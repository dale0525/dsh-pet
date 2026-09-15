"""从纯黑视频生成精确水印 mask：亮度>阈值 = 水印像素（黑背景无干扰）

用法: python make_mask_black.py [输出.mkv] [阈值] [纯黑视频.mp4]

纯黑参考视频的取法（按优先级）：命令行第 3 个参数 → 环境变量
`DSH_PET_BLACK_VIDEO` → 历史默认路径（Windows 开发机遗留）。三者都取不到
或文件不存在就直接报错退出——绝不拿一个不存在的文件静默跑出错误 mask。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from _tools import ffmpeg
except ImportError:
    from scripts._tools import ffmpeg

FFMPEG = ffmpeg()
BLACK_VIDEO_ENV = "DSH_PET_BLACK_VIDEO"
DEFAULT_BLACK_VIDEO = Path(r"D:\Source\windows\Downloads\生成10秒纯黑视频.mp4")


def resolve_black_video(override: Path | None = None) -> Path:
    """纯黑参考视频：命令行 → 环境变量 → 历史默认；都不存在则报错（fail-closed）。"""
    for candidate in (override, os.environ.get(BLACK_VIDEO_ENV) and Path(os.environ[BLACK_VIDEO_ENV]), DEFAULT_BLACK_VIDEO):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit(
        f"找不到纯黑参考视频。请显式给出：python make_mask_black.py <输出.mkv> <阈值> <纯黑视频.mp4>\n"
        f"  或设置环境变量 {BLACK_VIDEO_ENV}=/abs/path/to/black.mp4"
    )

W, H = 1280, 720
FPS = 24
DEFAULT_LUM_THRESH = 20


def make_mask(dst: Path, lum_thresh: int = DEFAULT_LUM_THRESH, black_video: Path | None = None) -> None:
    cmd = [FFMPEG, "-i", str(resolve_black_video(black_video)), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_size = W * H * 3
    mask_size = W * H
    frames = 0
    with open(dst.with_suffix(".raw"), "wb") as fw:
        while True:
            buf = proc.stdout.read(frame_size)
            if len(buf) < frame_size:
                break
            mask = bytearray(mask_size)
            for y in range(H):
                row = y * W * 3
                mrow = y * W
                for x in range(W):
                    i = row + x * 3
                    if (buf[i] + buf[i + 1] + buf[i + 2]) // 3 > lum_thresh:
                        mask[mrow + x] = 255
            fw.write(mask)
            frames += 1
    proc.stdout.close()
    proc.wait()
    print(f"分析帧数: {frames}")

    enc = [FFMPEG, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", str(dst.with_suffix(".raw")),
           "-c:v", "ffv1", "-pix_fmt", "gray", str(dst)]
    r = subprocess.run(enc)
    if r.returncode != 0:
        raise RuntimeError("mask 编码失败")
    dst.with_suffix(".raw").unlink()
    print(f"mask 已生成: {dst} ({dst.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "watermark_mask_precise.mkv"
    thresh = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_LUM_THRESH
    black = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    print(f"阈值: {thresh}")
    make_mask(dst, thresh, black)
