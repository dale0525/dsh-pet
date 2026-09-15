#!/usr/bin/env python3
"""Unit tests for dachshund green screen acceptance evaluator.

Tests cover:
1) Pure green PNG -> frame evaluation returns REVIEW/FAIL (fail-closed, no subject).
2) Green PNG with centered subject block -> quantitative checks and framing pass.
3) Pure green dogless MP4 (via ffmpeg lavfi) -> video evaluation returns REVIEW (not PASS),
   while container checks pass. (Specifically: test_dogless_pure_green_video_must_be_review)
4) Green MP4 with moving subject block -> displacement and start/end consistency are
   genuinely measured (numeric and range > 0).
5) Duration mismatch (--seconds vs actual duration) -> container check FAIL.
6) CLI interface in frames and video modes.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "pets" / "dachshund"))

from _tools import ffmpeg  # noqa: E402
import evaluate_dachshund as ev  # noqa: E402


class FrameEvaluationTests(unittest.TestCase):
    """Tests for single/multiple frame evaluation against §7.1."""

    def test_pure_green_frame_verdict_review_or_fail_closed(self):
        """1) 纯绿 PNG（864x480）-> 帧检查判 REVIEW/FAIL（无主体，fail-closed）。"""
        with tempfile.TemporaryDirectory(prefix="frame-eval-") as tmp:
            img_path = Path(tmp) / "pure_green.png"
            img = Image.new("RGB", (864, 480), (0, 255, 0))
            img.save(img_path)

            report = ev.evaluate_frame(img_path)

        self.assertIn(report["verdict"], ("REVIEW", "FAIL"))
        self.assertNotEqual(report["verdict"], "PASS")

        # Fail-closed: geometry checks must fail when subject is missing
        checks = report["checks"]
        self.assertFalse(checks["subject_center_x"]["passed"])
        self.assertFalse(checks["subject_height_fraction"]["passed"])
        self.assertIsNone(checks["subject_center_x"]["measured"])
        self.assertIsNone(checks["subject_height_fraction"]["measured"])

        # Green background checks should pass
        self.assertTrue(checks["green_background_fraction"]["passed"])
        self.assertGreaterEqual(checks["green_background_fraction"]["measured"], 0.70)
        self.assertTrue(checks["green_background_mean"]["passed"])
        self.assertTrue(checks["green_background_stddev"]["passed"])

    def test_green_with_centered_subject_passes(self):
        """2) 绿幕 + 明显居中的红色主体块 PNG -> 绿幕占比/构图项按阈值给出预期结论。"""
        with tempfile.TemporaryDirectory(prefix="frame-eval-") as tmp:
            img_path = Path(tmp) / "centered_dog.png"
            img = Image.new("RGB", (864, 480), (0, 255, 0))
            # Height: 384 px (384 / 480 = 0.80, in [0.70, 0.90])
            # Width: 200 px (centered at 432, 432 / 864 = 0.50, in [0.40, 0.60])
            # Foreground area: 200 * 384 = 76,800 px (76800 / 414720 = 18.52% fg, 81.48% bg >= 0.70)
            x1, y1 = 332, 48
            x2, y2 = 532, 432
            for x in range(x1, x2):
                for y in range(y1, y2):
                    img.putpixel((x, y), (220, 30, 30))
            img.save(img_path)

            report = ev.evaluate_frame(img_path)

        self.assertEqual(report["verdict"], "PASS")
        checks = report["checks"]
        self.assertTrue(checks["green_background_fraction"]["passed"])
        self.assertTrue(checks["green_background_mean"]["passed"])
        self.assertTrue(checks["green_background_stddev"]["passed"])
        self.assertTrue(checks["subject_center_x"]["passed"])
        self.assertTrue(checks["subject_height_fraction"]["passed"])

        self.assertAlmostEqual(checks["subject_center_x"]["measured"], 0.50, delta=0.02)
        self.assertAlmostEqual(checks["subject_height_fraction"]["measured"], 0.80, delta=0.02)

        # Visual inspection placeholders
        self.assertIn("identity_consistency", checks)
        self.assertIn("no_props", checks)
        self.assertEqual(checks["identity_consistency"]["status"], "MANUAL_VISUAL_REVIEW")
        self.assertEqual(checks["no_props"]["status"], "MANUAL_VISUAL_REVIEW")

    def test_off_center_subject_fails_composition(self):
        """Subject placed on the far left fails the center_x requirement."""
        with tempfile.TemporaryDirectory(prefix="frame-eval-") as tmp:
            img_path = Path(tmp) / "off_center.png"
            img = Image.new("RGB", (864, 480), (0, 255, 0))
            # x: 40 to 240 (center = 140 / 864 = 0.162 < 0.40)
            for x in range(40, 240):
                for y in range(48, 432):
                    img.putpixel((x, y), (220, 30, 30))
            img.save(img_path)

            report = ev.evaluate_frame(img_path)

        self.assertIn(report["verdict"], ("REVIEW", "FAIL"))
        self.assertFalse(report["checks"]["subject_center_x"]["passed"])


class VideoEvaluationTests(unittest.TestCase):
    """Tests for video evaluation against §7.2 and §7.4."""

    def _create_pure_green_video(self, directory: Path, duration_sec: float = 2.0) -> Path:
        target = directory / "pure_green.mp4"
        cmd = [
            ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=0x00FF00:s=864x480:r=24:d={duration_sec}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(target),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return target

    def _create_moving_subject_video(self, directory: Path, duration_sec: float = 2.0) -> Path:
        target = directory / "moving_block.mp4"
        # Moving box: x shifts horizontally with time using ffmpeg overlay filter
        cmd = [
            ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=0x00FF00:s=864x480:r=24:d={duration_sec}",
            "-f", "lavfi", "-i", f"color=c=red:s=120x320:d={duration_sec}",
            "-filter_complex", "[0:v][1:v]overlay=x=350+80*t:y=80",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(target),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return target

    def test_dogless_pure_green_video_must_be_review(self):
        """3) 纯绿无主体 864x480 / 24fps h264 mp4 -> 视频检查必须判 REVIEW（非 PASS），容器项通过。"""
        with tempfile.TemporaryDirectory(prefix="video-eval-") as tmp:
            video_path = self._create_pure_green_video(Path(tmp), duration_sec=2.0)
            report = ev.evaluate_video(video_path, expected_seconds=2.0)

        # §7.4 硬要求：必须判 REVIEW，绝不得静默 PASS
        self.assertEqual(report["verdict"], "REVIEW")
        self.assertNotEqual(report["verdict"], "PASS")

        checks = report["checks"]
        # 容器检查必须通过
        self.assertTrue(checks["container_resolution"]["passed"])
        self.assertTrue(checks["container_fps"]["passed"])
        self.assertTrue(checks["container_duration"]["passed"])
        self.assertTrue(checks["container_codec"]["passed"])

        # 5 点采样绿幕占比通过
        self.assertTrue(checks["green_matte_5point"]["passed"])

        # 扣像可用 / 几何等依赖主体的检查必须判失败（fail-closed）
        self.assertFalse(checks["chroma_keyable"]["passed"])
        self.assertFalse(checks["zero_displacement"]["passed"])
        self.assertFalse(checks["start_end_consistency"]["passed"])

    def test_moving_subject_video_calculates_displacement_and_consistency(self):
        """4) 绿幕 + 中央水平移动的方块 -> 零位移/首尾一致项被真实计算且位移极差 > 0。"""
        with tempfile.TemporaryDirectory(prefix="video-eval-") as tmp:
            video_path = self._create_moving_subject_video(Path(tmp), duration_sec=2.0)
            report = ev.evaluate_video(video_path, expected_seconds=2.0)

        checks = report["checks"]
        # 断言对应字段存在且是数值
        zero_disp = checks["zero_displacement"]
        self.assertIn("measured", zero_disp)
        self.assertIsInstance(zero_disp["measured"], (int, float))
        self.assertGreater(zero_disp["measured"], 0.0)

        # 同时也检查 metrics 中的汇总字段
        self.assertIn("center_x_range", report["metrics"])
        self.assertIsInstance(report["metrics"]["center_x_range"], (int, float))
        self.assertGreater(report["metrics"]["center_x_range"], 0.0)

        # 首尾一致性被真实计算且有位移差
        start_end = checks["start_end_consistency"]
        self.assertIn("measured", start_end)
        self.assertIsInstance(start_end["measured"], dict)
        self.assertIn("center_x_diff", start_end["measured"])
        self.assertIsInstance(start_end["measured"]["center_x_diff"], (int, float))
        self.assertGreater(start_end["measured"]["center_x_diff"], 0.0)

        # 因为有明显水平移动（极差大于 0.08），零位移检查应判失败
        self.assertFalse(zero_disp["passed"])

    def test_duration_mismatch_fails_container(self):
        """5) --seconds 与素材时长不匹配时（例如 2 秒素材要求 10 秒）容器项必须 FAIL。"""
        with tempfile.TemporaryDirectory(prefix="video-eval-") as tmp:
            video_path = self._create_pure_green_video(Path(tmp), duration_sec=2.0)
            report = ev.evaluate_video(video_path, expected_seconds=10.0)

        # 时长不匹配直接判 FAIL
        self.assertEqual(report["verdict"], "FAIL")
        self.assertFalse(report["checks"]["container_duration"]["passed"])
        self.assertAlmostEqual(report["checks"]["container_duration"]["measured"], 2.0, delta=0.1)

    def test_standing_points_fg_passes_even_when_5point_min_fg_below_threshold(self):
        """6) 判定取「站立采样点前景」而不是 5 点最小前景：
        构造 5 点最小 <0.15 但首末 (t=0, t=9.9) >=0.15 的用例，必须 PASS。
        """
        with tempfile.TemporaryDirectory(prefix="video-eval-") as tmp:
            video_path = Path(tmp) / "standing_pass_mid_dip.mp4"
            # Subject at t<1s and t>=9s: 200x384 (18.5% fg >= 0.15)
            # Subject at t in [1, 9]s: 100x200 (4.8% fg < 0.15)
            cmd = [
                ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=0x00FF00:s=864x480:r=24:d=10",
                "-f", "lavfi", "-i", "color=c=red:s=200x384:r=24:d=10",
                "-f", "lavfi", "-i", "color=c=red:s=100x200:r=24:d=10",
                "-filter_complex",
                "[0:v][1:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='lt(t,1)+gte(t,9)'[v1]; "
                "[v1][2:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='between(t,1,9)'",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(video_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            report = ev.evaluate_video(video_path, expected_seconds=10.0)

        # 5 点采样最小前景必须 < 0.15（参考值超标）
        self.assertLess(report["metrics"]["min_5point_foreground_reference"], 0.15)
        # 站立采样点 (首末) 必须 >= 0.15（决定值达标）
        standing_dec = report["metrics"]["standing_foreground_decision"]
        self.assertGreaterEqual(standing_dec["t0"], 0.15)
        self.assertGreaterEqual(standing_dec["t9_9"], 0.15)
        self.assertGreaterEqual(standing_dec["min_standing"], 0.15)

        # 门禁判定必须为 PASS（不再因 5 点最小低谷而误判 FAIL/REVIEW）
        self.assertTrue(report["checks"]["chroma_keyable"]["passed"])
        self.assertEqual(report["verdict"], "PASS")

    def test_deliverable_green_spill_passes_even_when_raw_spill_above_threshold(self):
        """7) 绿溢判定取交付物值：
        构造原始绿溢超标 (>2%) 但交付物 <=2% 的用例，必须 PASS。
        """
        with tempfile.TemporaryDirectory(prefix="video-eval-") as tmp:
            raw_path = Path(tmp) / "raw_spill_high.mp4"
            # Raw subject with 5% green spill edge:
            # Base green canvas: 864x480
            # Red block: 190x384 at x=342, y=48
            # Green fringe: 10x384 of RGB(100, 135, 100) (0x648764) at x=332, y=48 -> spill = 5% > 2%
            cmd_raw = [
                ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=0x00FF00:s=864x480:r=24:d=10",
                "-f", "lavfi", "-i", "color=c=0x648764:s=10x384:r=24:d=10",
                "-f", "lavfi", "-i", "color=c=red:s=190x384:r=24:d=10",
                "-filter_complex", "[0:v][1:v]overlay=x=332:y=48[v1]; [v1][2:v]overlay=x=342:y=48",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(raw_path),
            ]
            subprocess.run(cmd_raw, check=True, capture_output=True)

            # Deliverable webm (640x360 VP9+alpha) with pure red subject (spill = 0%)
            keyed_path = Path(tmp) / "deliverable_clean.webm"
            cmd_keyed = [
                ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black@0.0:s=640x360:r=24:d=10,format=yuva420p",
                "-f", "lavfi", "-i", "color=c=red:s=160x280:r=24:d=10,format=yuva420p",
                "-filter_complex", "[0:v][1:v]overlay=x=(W-w)/2:y=(H-h)/2:format=auto",
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                str(keyed_path),
            ]
            subprocess.run(cmd_keyed, check=True, capture_output=True)

            # Evaluate with deliverable counterpart supplied
            report = ev.evaluate_video(raw_path, expected_seconds=10.0, deliverable_path=keyed_path)

        # 原始绿溢超标（参考值）
        self.assertGreater(report["metrics"]["raw_spill_reference"], 0.02)
        # 交付物绿溢达标（决定值 <= 0.02）
        self.assertLessEqual(report["metrics"]["deliverable_spill_decision"], 0.02)
        self.assertTrue(report["checks"]["green_spill"]["passed"])
        self.assertIn("deliverable spill <= 0.02 (ruled 2026-09-02)", report["checks"]["green_spill"]["threshold"])
        self.assertEqual(report["verdict"], "PASS")

    def test_keyed_deliverable_mode_container_and_evaluation(self):
        """8) 交付物模式评测 640x360 VP9+alpha WebM 容器与度量项。"""
        with tempfile.TemporaryDirectory(prefix="video-eval-") as tmp:
            keyed_path = Path(tmp) / "clip.webm"
            cmd = [
                ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black@0.0:s=640x360:r=24:d=10,format=yuva420p",
                "-f", "lavfi", "-i", "color=c=red:s=160x280:r=24:d=10,format=yuva420p",
                "-filter_complex", "[0:v][1:v]overlay=x=(W-w)/2:y=(H-h)/2:format=auto",
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                str(keyed_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            report = ev.evaluate_video(keyed_path, expected_seconds=10.0)

        self.assertEqual(report["container"]["width"], 640)
        self.assertEqual(report["container"]["height"], 360)
        self.assertEqual(report["container"]["video_codec"], "vp9")
        self.assertTrue(report["checks"]["container_resolution"]["passed"])
        self.assertTrue(report["checks"]["container_codec"]["passed"])
        self.assertTrue(report["checks"]["container_fps"]["passed"])
        self.assertTrue(report["checks"]["container_duration"]["passed"])
        self.assertLessEqual(report["metrics"]["deliverable_spill_decision"], 0.02)


class CliTests(unittest.TestCase):
    """Tests for CLI argument parsing and execution."""

    def test_cli_frames_mode(self):
        with tempfile.TemporaryDirectory(prefix="cli-eval-") as tmp:
            img_path = Path(tmp) / "frame.png"
            out_json = Path(tmp) / "out.json"
            img = Image.new("RGB", (864, 480), (0, 255, 0))
            img.save(img_path)

            ret = ev.main(["frames", str(img_path), "--json", str(out_json)])
            # Since frame has no subject, verdict is REVIEW -> exit code non-zero
            self.assertNotEqual(ret, 0)
            self.assertTrue(out_json.is_file())
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "frames")
            self.assertIn("frames", data)

    def test_cli_video_mode(self):
        with tempfile.TemporaryDirectory(prefix="cli-eval-") as tmp:
            video_path = Path(tmp) / "clip.mp4"
            out_json = Path(tmp) / "out.json"
            cmd = [
                ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=0x00FF00:s=864x480:r=24:d=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(video_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            ret = ev.main(["video", str(video_path), "--seconds", "2.0", "--json", str(out_json)])
            self.assertNotEqual(ret, 0)  # Pure green is REVIEW -> exit code 1
            self.assertTrue(out_json.is_file())
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "video")
            self.assertEqual(data["verdict"], "REVIEW")

    def test_cli_video_keyed_mode_and_metrics_output(self):
        """CLI 交付物模式支持 --keyed，并在输出中包含四个澄清度量项。"""
        with tempfile.TemporaryDirectory(prefix="cli-eval-") as tmp:
            keyed_path = Path(tmp) / "clip.webm"
            out_json = Path(tmp) / "out.json"
            cmd = [
                ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black@0.0:s=640x360:r=24:d=10,format=yuva420p",
                "-f", "lavfi", "-i", "color=c=red:s=160x280:r=24:d=10,format=yuva420p",
                "-filter_complex", "[0:v][1:v]overlay=x=(W-w)/2:y=(H-h)/2:format=auto",
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                str(keyed_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            ret = ev.main(["video", str(keyed_path), "--seconds", "10.0", "--keyed", "--json", str(out_json)])
            self.assertEqual(ret, 0)
            self.assertTrue(out_json.is_file())
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "video")
            self.assertEqual(data["verdict"], "PASS")
            # 校验四个度量项名称
            metrics = data["metrics"]
            self.assertIn("deliverable_spill_decision", metrics)
            self.assertIn("raw_spill_reference", metrics)
            self.assertIn("standing_foreground_decision", metrics)
            self.assertIn("min_5point_foreground_reference", metrics)


if __name__ == "__main__":
    unittest.main()

