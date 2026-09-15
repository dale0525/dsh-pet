"""bridge_step00.py - Bridge upstream H3 video (864x480) to downstream 1280x720.

契约规格：
- 默认 SRC = <repo>/step00，OUT = <repo>/step01（step01 正是 chroma_step02.py 的 SRC）。
- CLI: python scripts/bridge_step00.py [--src DIR] [--out DIR] [file.mp4 ...]
  - 无位置参数：处理 SRC 下全部 *.mp4；一个都没有则非 0 退出。
  - 有位置参数：只处理这些文件。
- 缩放/编码：-vf scale=1280:720:flags=lanczos -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -an
- 若源不是 16:9 必须报错并退出（fail-closed），不要静默拉伸变形。
  阈值：`(864, 480)` 是 H3 契约输出，显式放行；其余按 |w/h - 16/9| <= 0.03 判定。
  0.03 而非 0.01 是实测倒推的：864x480 实为 1.8:1，与 16/9 差 0.0222——
  按 0.01 卡会把唯一合法的上游输入拒掉。
- 幂等/断点续跑：输出已存在、且比源新、且 ffprobe 能读到视频流 -> 打印 SKIP，不重编码。
- ffmpeg/ffprobe 从 scripts/_tools.py 取，禁止写死绝对路径。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# 确保能 import 到同目录下的 _tools.py
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _tools import ffmpeg, ffprobe

ROOT = _SCRIPTS_DIR.parent
DEFAULT_SRC = ROOT / "step00"
DEFAULT_OUT = ROOT / "step01"


def probe_video_streams(path: Path) -> list[dict]:
    """读取视频文件中的视频流信息，读取失败或无视频流返回空列表。"""
    cmd = [
        ffprobe(),
        "-v", "error",
        "-select_streams", "v",
        "-show_entries", "stream=width,height,codec_name,r_frame_rate,pix_fmt",
        "-of", "json",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return []
    try:
        data = json.loads(res.stdout)
        return [s for s in data.get("streams", []) if s.get("width") and s.get("height")]
    except Exception:
        return []


def is_16_9(w: int, h: int) -> bool:
    """检查画面比例是否符合 16:9 契约。

    上游 H3 视频生成固定输出 864x480 (864/480 = 1.8)，系 16 宏块对齐的 16:9 近似
    （与 16/9 差异约为 0.0222）。针对非 16:9 变形源（如 800x600 差异 0.444）严格报错退出，
    特许 (864, 480) 契约输入或通用容差 0.03 内的 16:9 源。
    """
    if (w, h) == (864, 480):
        return True
    return abs(w / h - 16 / 9) <= 0.03


def process_video(src_path: Path, out_dir: Path) -> None:
    """处理单个视频文件。"""
    if not src_path.is_file():
        sys.stderr.write(f"Error: Source file does not exist: {src_path}\n")
        sys.exit(1)

    streams = probe_video_streams(src_path)
    if not streams:
        sys.stderr.write(f"Error: Could not read video streams from {src_path}\n")
        sys.exit(1)

    v = streams[0]
    w = int(v["width"])
    h = int(v["height"])

    if not is_16_9(w, h):
        diff = abs(w / h - 16 / 9)
        sys.stderr.write(
            f"Error: {src_path} is not 16:9 aspect ratio ({w}x{h}, diff {diff:.4f} > 0.03)\n"
        )
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / src_path.name

    # 幂等/断点续跑：输出已存在、且比源新、且 ffprobe 能读到视频流 -> SKIP
    if out_path.is_file():
        src_mtime = src_path.stat().st_mtime_ns
        out_mtime = out_path.stat().st_mtime_ns
        if out_mtime > src_mtime:
            out_streams = probe_video_streams(out_path)
            if out_streams:
                print(f"SKIP: {out_path.name} is newer than source and valid.")
                return

    cmd = [
        ffmpeg(),
        "-y",
        "-i", str(src_path),
        "-vf", "scale=1280:720:flags=lanczos",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "16",
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        sys.stderr.write(f"Error: ffmpeg failed for {src_path}:\n{res.stderr}\n")
        sys.exit(res.returncode)

    print(f"ENCODE: {src_path.name} -> {out_path.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bridge upstream 864x480 video to downstream 1280x720 video."
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=DEFAULT_SRC,
        help=f"Source directory containing input mp4 files (default: {DEFAULT_SRC})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory for bridged mp4 files (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Optional specific mp4 files to process. If omitted, processes all *.mp4 in --src.",
    )

    args = parser.parse_args(argv)

    if args.files:
        files_to_process = args.files
    else:
        args.src.mkdir(parents=True, exist_ok=True)
        files_to_process = sorted(args.src.glob("*.mp4"))
        if not files_to_process:
            sys.stderr.write(f"Error: No *.mp4 files found in {args.src}\n")
            return 1

    for f in files_to_process:
        process_video(f, args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
