"""test_bridge_step00.py - Unit tests for scripts/bridge_step00.py."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# 让测试能 import 到 scripts/ 下的模块
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _tools import ffmpeg, ffprobe

SCRIPT_PATH = SCRIPTS_DIR / "bridge_step00.py"
FIXTURE_PATH = REPO_ROOT / "test" / "pet1" / "h3-out" / "output.mp4"


def probe_video(path: Path) -> dict:
    """Read stream and format info using ffprobe."""
    cmd = [
        ffprobe(),
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


class TestBridgeStep00(unittest.TestCase):
    def setUp(self):
        self.tmp_dirs: list[Path] = []

    def tearDown(self):
        for d in self.tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _make_temp_dir(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="test_bridge_"))
        self.tmp_dirs.append(d)
        return d

    def test_01_real_fixture_bridge(self):
        """1) 用真实的 test/pet1/h3-out/output.mp4 作夹具（864×480）：

        桥接产物 ffprobe 必须是 1280×720 / 24fps / h264 / yuv420p，且时长与源一致（±0.05s）。
        """
        self.assertTrue(
            FIXTURE_PATH.is_file(),
            "缺夹具（test/pet1/ 按规格 §11 裁定 5 不纳入 git，干净克隆里没有）：\n"
            f"  {FIXTURE_PATH}\n"
            "  补救：从产出它的机器取回 test/pet1/h3-out/output.mp4（864x480/24fps/h264）。"
            "此断言故意是失败而非跳过——门禁不静默放行。",
        )
        src_probe = probe_video(FIXTURE_PATH)
        src_duration = float(src_probe["format"]["duration"])

        out_dir = self._make_temp_dir()
        cmd = [
            sys.executable,
            str(SCRIPT_PATH),
            "--out",
            str(out_dir),
            str(FIXTURE_PATH),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Process failed: {res.stderr}")

        out_file = out_dir / FIXTURE_PATH.name
        self.assertTrue(out_file.is_file(), f"Expected output file: {out_file}")

        out_probe = probe_video(out_file)
        video_streams = [s for s in out_probe["streams"] if s.get("codec_type") == "video"]
        audio_streams = [s for s in out_probe["streams"] if s.get("codec_type") == "audio"]

        self.assertEqual(len(video_streams), 1, "Expected exactly 1 video stream")
        self.assertEqual(len(audio_streams), 0, "Audio stream must be stripped (-an)")

        v = video_streams[0]
        self.assertEqual(v["width"], 1280)
        self.assertEqual(v["height"], 720)
        self.assertEqual(v["codec_name"], "h264")
        self.assertEqual(v["pix_fmt"], "yuv420p")

        # fps check
        r_num, r_den = map(int, v["r_frame_rate"].split("/"))
        fps = r_num / r_den
        self.assertAlmostEqual(fps, 24.0, delta=0.01)

        # duration check: ±0.05s
        out_duration = float(out_probe["format"]["duration"])
        self.assertAlmostEqual(out_duration, src_duration, delta=0.05)

    def test_02_custom_output_and_batch_directory(self):
        """2) 输出目录可自定义（用 tmpdir），不污染仓库目录。

        无位置参数：处理 SRC 下全部 *.mp4；一个都没有则非 0 退出。
        """
        src_dir = self._make_temp_dir()
        out_dir = self._make_temp_dir()

        # 验证一个都没有时退出码非 0
        cmd_empty = [
            sys.executable,
            str(SCRIPT_PATH),
            "--src",
            str(src_dir),
            "--out",
            str(out_dir),
        ]
        res_empty = subprocess.run(cmd_empty, capture_output=True, text=True)
        self.assertNotEqual(res_empty.returncode, 0, "Should exit non-zero when no *.mp4 found")

        # 放入两个测试 mp4
        file_a = src_dir / "sample_a.mp4"
        file_b = src_dir / "sample_b.mp4"
        shutil.copy2(FIXTURE_PATH, file_a)
        shutil.copy2(FIXTURE_PATH, file_b)

        # 批量处理
        cmd_batch = [
            sys.executable,
            str(SCRIPT_PATH),
            "--src",
            str(src_dir),
            "--out",
            str(out_dir),
        ]
        res_batch = subprocess.run(cmd_batch, capture_output=True, text=True)
        self.assertEqual(res_batch.returncode, 0, f"Batch process failed: {res_batch.stderr}")

        out_a = out_dir / "sample_a.mp4"
        out_b = out_dir / "sample_b.mp4"
        self.assertTrue(out_a.is_file(), f"Missing {out_a}")
        self.assertTrue(out_b.is_file(), f"Missing {out_b}")

        probe_a = probe_video(out_a)
        self.assertEqual(probe_a["streams"][0]["width"], 1280)
        self.assertEqual(probe_a["streams"][0]["height"], 720)

    def test_03_non_16_9_fails_closed(self):
        """3) 非 16:9 源（用 800x600 小夹具）必须报错/非 0 退出。"""
        src_dir = self._make_temp_dir()
        out_dir = self._make_temp_dir()
        bad_video = src_dir / "bad_ratio_800x600.mp4"

        # 生成 800x600 24fps 1s 测试夹具 (4:3)
        gen_cmd = [
            ffmpeg(),
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=size=800x600:rate=24",
            "-t", "1",
            "-pix_fmt", "yuv420p",
            str(bad_video),
        ]
        subprocess.run(gen_cmd, capture_output=True, text=True, check=True)

        cmd = [
            sys.executable,
            str(SCRIPT_PATH),
            "--out",
            str(out_dir),
            str(bad_video),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0, "Non-16:9 input must fail with non-zero exit code")
        self.assertFalse((out_dir / bad_video.name).exists(), "Must not write output for invalid ratio")

    def test_04_breakpoint_resume_idempotency(self):
        """4) 断点续跑：第二次运行同一文件返回 SKIP（输出文件 mtime 与内容不变）。"""
        out_dir = self._make_temp_dir()
        cmd = [
            sys.executable,
            str(SCRIPT_PATH),
            "--out",
            str(out_dir),
            str(FIXTURE_PATH),
        ]

        # 第一次运行
        res1 = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0, f"Run 1 failed: {res1.stderr}")

        out_file = out_dir / FIXTURE_PATH.name
        self.assertTrue(out_file.is_file())
        stat1 = out_file.stat()
        mtime1 = stat1.st_mtime_ns
        hash1 = hashlib.sha256(out_file.read_bytes()).hexdigest()

        # 等待微小间隔，确保第二次运行若重新编码会变更 mtime
        time.sleep(0.05)

        # 第二次运行
        res2 = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0, f"Run 2 failed: {res2.stderr}")
        self.assertIn("SKIP", res2.stdout, f"Expected SKIP in stdout, got: {res2.stdout}")

        stat2 = out_file.stat()
        mtime2 = stat2.st_mtime_ns
        hash2 = hashlib.sha256(out_file.read_bytes()).hexdigest()

        self.assertEqual(mtime1, mtime2, "Output file mtime changed despite skip")
        self.assertEqual(hash1, hash2, "Output file content changed despite skip")


if __name__ == "__main__":
    unittest.main()
