"""断点续跑完整性检查必须能发现**被截断**的产物。

来由（实测事故）：第一次整链运行因超时被 SIGTERM 打断，`step02/爪拨玩具小车.webm`
只写了 147/240 帧（6.125s），但它的体积 > 50KB、mtime 比源新、ffprobe 也能读到视频流，
于是旧版 `_is_valid` 判它「有效」，后续所有重跑都 SKIP 它——
结果这条动作以 6 秒的残缺成片混进了最终 pet pack（装配后才发现）。

教训：只查「存在 + 够大 + 不旧 + 能解码」不足以证明产物完整，
**必须比对时长**（最便宜且直接反映「有没有写完」）。
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import chroma_step02  # noqa: E402
import encode_thumbs  # noqa: E402
import normalize_step03  # noqa: E402
from _tools import ffmpeg  # noqa: E402

TMP = REPO / "pets/dachshund/.tmp-truncation"
FFMPEG = str(ffmpeg())


def make_clip(path: Path, seconds: float, size: str = "640x360") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=24:duration={seconds}",
         "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", str(path)],
        check=True,
    )
    return path


class TestTruncationDetected(unittest.TestCase):
    """三个步骤脚本的 `_is_valid` 都必须对截断产物返回 False。"""

    @classmethod
    def setUpClass(cls):
        TMP.mkdir(parents=True, exist_ok=True)
        # 尺寸取 640x360 且 CRF 低，保证**截断的那份也超过 min_size（50KB）**——
        # 否则它是被「体积不够」拒掉，测试就证明不了「时长比对」这条新判据真的生效。
        cls.src = make_clip(TMP / "src.webm", 10.0)
        cls.truncated = make_clip(TMP / "truncated.webm", 6.0)
        cls.complete = make_clip(TMP / "complete.webm", 10.0)
        for p in (cls.truncated, cls.complete):
            assert p.stat().st_size > 50_000, f"{p.name} 太小（{p.stat().st_size}B），测不到时长判据"
        # 让两者的 mtime 都新于源，排除「比源旧」这条判据的干扰——
        # 即：只有时长比对才能把它们区分开。
        import os, time

        future = time.time() + 5
        for p in (cls.truncated, cls.complete):
            os.utime(p, (future, future))

    @classmethod
    def tearDownClass(cls):
        for p in TMP.glob("*"):
            p.unlink()
        TMP.rmdir()

    def test_small_truncation_is_rejected(self):
        """**几帧**的截断也必须被发现——0.2s 容差会放过 4.8 帧，等于漏报。

        真实链路里 webm 与源 mp4 的自然量化差实测最大仅 0.0410s（≈1 帧，见 §17.5），
        所以容差收紧到 0.09s（≈2.2 帧）：放过全部真实产物，却抓得住 ≥3 帧的截断。
        """
        src = make_clip(TMP / "small-src.webm", 240 / 24)      # 10.000s
        one_frame_off = make_clip(TMP / "one-frame.webm", 239 / 24)   # 9.958s（真实自然量化差）
        four_frames_off = make_clip(TMP / "four-frames.webm", 236 / 24)  # 9.833s（4 帧截断）
        for p in (src, one_frame_off, four_frames_off):
            assert p.stat().st_size > 50_000, f"{p.name} 太小（{p.stat().st_size}B），测不到时长判据"
        self.addCleanup(lambda: [p.unlink() for p in (src, one_frame_off, four_frames_off)])
        mods = (chroma_step02, normalize_step03, encode_thumbs)
        for mod in mods:
            self.assertTrue(mod._is_valid(one_frame_off, src), f"{mod.__name__}: 1 帧自然差被误判为截断")
            self.assertFalse(mod._is_valid(four_frames_off, src), f"{mod.__name__}: 4 帧截断被放过")

    def test_chroma_rejects_truncated(self):
        self.assertFalse(chroma_step02._is_valid(self.truncated, self.src), "截断的 webm 被判为有效")
        self.assertTrue(chroma_step02._is_valid(self.complete, self.src), "完整产物被判为无效（会导致无谓重算）")

    def test_normalize_rejects_truncated(self):
        self.assertFalse(normalize_step03._is_valid(self.truncated, self.src))
        self.assertTrue(normalize_step03._is_valid(self.complete, self.src))

    def test_thumbs_reject_truncated(self):
        self.assertFalse(encode_thumbs._is_valid(self.truncated, self.src))
        self.assertTrue(encode_thumbs._is_valid(self.complete, self.src))

    def test_missing_file_is_invalid(self):
        """不存在的产物仍然必须返回 False（原有行为不能退化）。"""
        missing = TMP / "nope.webm"
        for mod in (chroma_step02, normalize_step03, encode_thumbs):
            self.assertFalse(mod._is_valid(missing, self.src))


if __name__ == "__main__":
    unittest.main()
