"""素材处理链管线工具解析与常量定义测试。

验证：
1. scripts/*.py 中不得再出现 hardcoded Windows ffmpeg-9.0.1 路径、.tools 路径及 .exe 字面量（_tools.py 自身除外）。
2. scripts/chroma_step02.py 中 GREEN_HUE_MIN 与 GREEN_HUE_MAX 仅各赋值一次（AST 统计），无重复死定义，运行时行为一致。
3. 8 个管线脚本的 FFMPEG/FFPROBE 正确指向 _tools.ffmpeg()/_tools.ffprobe() 且真实存在。
"""

from __future__ import annotations

import ast
import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"

# 保证 scripts 目录在 sys.path
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _tools

PIPELINE_MODULES_ALL = [
    "chroma_step02",
    "encode_preview_gifs",
    "encode_thumbs",
    "fill_nn",
    "make_mask_black",
    "normalize_step03",
    "pr_import_step02",
    "watermark_step01",
]

MODULES_WITH_FFPROBE = {
    "chroma_step02",
    "encode_thumbs",
    "normalize_step03",
    "pr_import_step02",
    "watermark_step01",
}


class TestScriptsTools(unittest.TestCase):
    """测试管线脚本的工具路径解析与常量定义规范。"""

    def test_no_hardcoded_tools_in_scripts(self) -> None:
        """扫描 scripts/*.py：无 ffmpeg-9.0.1、无 .tools 路径、无 .exe 字面量（_tools.py 例外）。"""
        py_files = sorted(SCRIPTS_DIR.glob("*.py"))
        self.assertGreater(len(py_files), 0, "scripts 目录下未发现 Python 文件")

        for py_file in py_files:
            # _tools.py 是单一真源本身，支持 Windows 候选路径解析并包含历史演进注释
            if py_file.name == "_tools.py":
                continue

            content = py_file.read_text(encoding="utf-8")

            # 不得再出现 ffmpeg-9.0.1
            self.assertNotIn(
                "ffmpeg-9.0.1",
                content,
                f"{py_file.name} 中仍包含 'ffmpeg-9.0.1' 路径",
            )

            # 不得出现 .tools 路径
            self.assertNotIn(
                ".tools",
                content,
                f"{py_file.name} 中仍包含 '.tools' 路径",
            )

            # 不得出现 .exe 字面量
            self.assertNotIn(
                ".exe",
                content,
                f"{py_file.name} 中仍包含 '.exe' 字面量",
            )

    def test_chroma_step02_constants_single_source(self) -> None:
        """chroma_step02.py 中 GREEN_HUE_MIN 与 GREEN_HUE_MAX 各只被赋值一次，无死定义。"""
        chroma_file = SCRIPTS_DIR / "chroma_step02.py"
        self.assertTrue(chroma_file.is_file(), "chroma_step02.py 不存在")

        tree = ast.parse(chroma_file.read_text(encoding="utf-8"), filename=str(chroma_file))

        assign_counts: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assign_counts[target.id] = assign_counts.get(target.id, 0) + 1
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    assign_counts[node.target.id] = assign_counts.get(node.target.id, 0) + 1

        self.assertEqual(
            assign_counts.get("GREEN_HUE_MIN", 0),
            1,
            f"GREEN_HUE_MIN 被赋值 {assign_counts.get('GREEN_HUE_MIN', 0)} 次，应为 1 次",
        )
        self.assertEqual(
            assign_counts.get("GREEN_HUE_MAX", 0),
            1,
            f"GREEN_HUE_MAX 被赋值 {assign_counts.get('GREEN_HUE_MAX', 0)} 次，应为 1 次",
        )

        # 验证运行时导入后的常量一致性：色相与阈值各只有一套定义
        mod = importlib.import_module("chroma_step02")
        self.assertEqual(mod.GREEN_HUE_MIN, 70.0)
        self.assertEqual(mod.GREEN_HUE_MAX, 170.0)
        self.assertEqual(mod.SAT_MIN, 0.15)
        self.assertEqual(mod.VAL_MIN, 0.15)
        # 历史上 SAT_MIN/VAL_MIN 与 SATURATION_MIN/VALUE_MIN 两套并存（后者是死定义）；
        # 合并后只保留一套，别名必须彻底消失，否则又会长回双份定义。
        for alias in ("SATURATION_MIN", "VALUE_MIN"):
            self.assertFalse(
                hasattr(mod, alias),
                f"{alias} 是被合并掉的旧别名，不应再存在（见规格 §14.5 常量去重）",
            )

    def test_pipeline_scripts_ffmpeg_ffprobe(self) -> None:
        """8 个管线模块的 FFMPEG/FFPROBE 指向真实存在的文件且等于 _tools 的解析结果。"""
        expected_ffmpeg = _tools.ffmpeg()
        expected_ffprobe = _tools.ffprobe()

        self.assertTrue(os.path.isfile(expected_ffmpeg), f"ffmpeg 二进制不存在: {expected_ffmpeg}")
        self.assertTrue(os.path.isfile(expected_ffprobe), f"ffprobe 二进制不存在: {expected_ffprobe}")

        for mod_name in PIPELINE_MODULES_ALL:
            with self.subTest(module=mod_name):
                # 重新导入或获取已导入模块
                if mod_name in sys.modules:
                    mod = importlib.reload(sys.modules[mod_name])
                else:
                    mod = importlib.import_module(mod_name)

                # 必须拥有 FFMPEG 且指向真实文件，与 _tools.ffmpeg() 相等
                self.assertTrue(hasattr(mod, "FFMPEG"), f"{mod_name} 缺少 FFMPEG 常量")
                self.assertEqual(
                    mod.FFMPEG,
                    expected_ffmpeg,
                    f"{mod_name}.FFMPEG ({mod.FFMPEG}) != expected ({expected_ffmpeg})",
                )
                self.assertTrue(
                    os.path.isfile(mod.FFMPEG),
                    f"{mod_name}.FFMPEG 文件不存在: {mod.FFMPEG}",
                )

                # 若属于定义了 FFPROBE 的管线脚本，必须相等且文件存在
                if mod_name in MODULES_WITH_FFPROBE:
                    self.assertTrue(hasattr(mod, "FFPROBE"), f"{mod_name} 缺少 FFPROBE 常量")
                    self.assertEqual(
                        mod.FFPROBE,
                        expected_ffprobe,
                        f"{mod_name}.FFPROBE ({mod.FFPROBE}) != expected ({expected_ffprobe})",
                    )
                    self.assertTrue(
                        os.path.isfile(mod.FFPROBE),
                        f"{mod_name}.FFPROBE 文件不存在: {mod.FFPROBE}",
                    )


if __name__ == "__main__":
    unittest.main()
