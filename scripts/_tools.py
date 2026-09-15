"""素材处理链的公共二进制解析：ffmpeg / ffprobe（单一真源）。

历史上 8 个管线脚本各自写死了 Windows 专用绝对路径
`.tools/ffmpeg-9.0.1-essentials_build/bin/*.exe`，在 macOS/Linux 上全部跑不了。
本模块是该事实的唯一真源：**所有管线脚本一律从这里取路径**，不得再写死。

解析顺序（先命中先用）：
1. 环境变量 `DSH_PET_FFMPEG` / `DSH_PET_FFPROBE`——显式覆盖，最高优先级
2. `PATH`（`shutil.which`）——`pixi run <task>` 下即 pixi 环境的 bin 目录
3. 本仓库 pixi 环境：`<repo>/.pixi/envs/*/bin/<name>`（Windows 为 `Scripts/<name>.exe`）
4. 常见绝对安装位置（Homebrew、/usr/local、同机器其他 pixi 环境）

四处都找不到就抛 `ToolMissing`，并给出可操作的补救命令——**不静默回落**。
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 常见绝对安装位置（仅作兜底，不假定存在）
_FALLBACK_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)


class ToolMissing(RuntimeError):
    """管线所需的外部二进制在本机找不到。"""


def _env_var(name: str) -> str:
    return f"DSH_PET_{name.upper()}"


def _candidates(name: str) -> list[Path]:
    """按解析顺序给出候选路径（`name` 是不带扩展名的工具名，如 ffmpeg）。"""
    out: list[Path] = []

    override = os.environ.get(_env_var(name))
    if override:
        out.append(Path(override).expanduser())

    found = shutil.which(name)
    if found:
        out.append(Path(found))

    # 本仓库 pixi 环境（环境名任意：default / dev / …）
    envs = ROOT / ".pixi" / "envs"
    if envs.is_dir():
        for env in sorted(envs.iterdir()):
            out.append(env / "bin" / name)
            out.append(env / "Scripts" / f"{name}.exe")
            out.append(env / "Library" / "bin" / f"{name}.exe")

    for directory in _FALLBACK_DIRS:
        out.append(directory / name)
        out.append(directory / f"{name}.exe")

    return out


@functools.lru_cache(maxsize=None)
def tool(name: str) -> str:
    """解析工具路径；找不到抛 `ToolMissing`（附补救命令）。"""
    for path in _candidates(name):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise ToolMissing(
        f"找不到 {name}。三条补救路径（任选其一）：\n"
        f"  1) pixi run <task>            # 用仓库 pixi 环境（pixi.toml 已声明 ffmpeg）\n"
        f"  2) export {_env_var(name)}=/abs/path/to/{name}\n"
        f"  3) brew install ffmpeg        # 或系统包管理器（本仓库不推荐全局安装）"
    )


def ffmpeg() -> str:
    """ffmpeg 可执行文件路径。"""
    return tool("ffmpeg")


def ffprobe() -> str:
    """ffprobe 可执行文件路径。"""
    return tool("ffprobe")


# 逐级产物与上级产物的允许时长差（秒）。判据见 same_duration 的 docstring。
MAX_DURATION_DRIFT = 0.09


def video_duration(path: Path) -> float | None:
    """视频时长（秒）；读不到返回 None。

    为什么需要它：各步骤脚本的「断点续跑」原本只查「存在 + 够大 + 不旧 + 能解码」，
    **查不出被截断的产物**——进程被 Ctrl-C / 超时杀掉时，webm 经常是完整可解码的
    前缀（实测事故：`step02/爪拨玩具小车.webm` 只写了 147/240 帧 = 6.125s，
    体积、mtime、可解码性三项全部通过，于是所有重跑都 SKIP 它，
    残缺成片一路混进了最终 pet pack）。
    时长是最便宜且直接反映「有没有写完」的判据。
    """
    result = subprocess.run(
        # 注意：查的是 format 级时长，`-select_streams` 对它不起作用（别再加回来）。
        [ffprobe(), "-v", "error",
         "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return None


def same_duration(dst: Path, src: Path, tolerance: float = MAX_DURATION_DRIFT) -> bool:
    """`dst` 的时长是否与 `src` 一致（容差默认见 `MAX_DURATION_DRIFT`）。

    容差为何不是 0：VP9/webm 常比源 mp4 少报 1 帧（实测 240 帧：mp4 = 10.000s，
    webm = 9.959s，差 0.041s）。
    容差为何也不能太宽：24fps 下 0.2s = 4.8 帧，会**放过 4 帧级的截断**（实测确认）。
    取 0.09s ≈ 2.2 帧：全链 20 条实测最大自然差仅 0.0410s（≈1 帧），留 2.2× 余量，
    同时任何 ≥3 帧（0.125s）的截断都会被抓出来。
    """
    a, b = video_duration(dst), video_duration(src)
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance

