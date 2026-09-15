"""frame_plate.reframe 的单测：把主体放大到目标高度占比，且必须保持 16:9、居中、镜像等变。

为什么要有这个函数（实测倒推，见规格 §16）：
H3 成片的「前景占比」比底板低 20–26%（压缩后毛发边缘被判成绿幕），
而 §7.2 要求抠像前景 ≥ 0.15。底板主体只有 0.819 高度占比时，成片前景会掉到 0.149–0.162，
贴着阈值。把底板主体放大到 ~0.865 后成片前景回到 0.16–0.18，才留出余量。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import frame_plate  # noqa: E402

GREEN = (3, 249, 7)
SIZE = (1672, 941)


def synthetic(height_fraction: float = 0.60, offset_x: int = 0) -> Image.Image:
    """绿幕底 + 一个居中（可偏移）的棕色矩形当主体。"""
    img = Image.new("RGB", SIZE, GREEN)
    aw = int(SIZE[0] * 0.40)
    ah = int(SIZE[1] * height_fraction)
    box = Image.new("RGB", (aw, ah), (190, 110, 40))
    img.paste(box, ((SIZE[0] - aw) // 2 + offset_x, (SIZE[1] - ah) // 2))
    return img


def subject_height_fraction(img: Image.Image) -> float:
    arr = np.asarray(img).astype(np.int16)
    bg = frame_plate.background_mask(arr)
    ys, _ = np.where(~bg)
    return (ys.max() - ys.min() + 1) / img.size[1]


def subject_center_x(img: Image.Image) -> float:
    arr = np.asarray(img).astype(np.int16)
    bg = frame_plate.background_mask(arr)
    _, xs = np.where(~bg)
    return (xs.min() + xs.max()) / 2 / img.size[0]


class TestReframe(unittest.TestCase):
    def test_scales_subject_to_target_height(self):
        """目标 0.86：实测高度占比必须落在目标 ±0.02 内。"""
        out = frame_plate.reframe(synthetic(0.60), 0.86, SIZE)
        self.assertEqual(out.size, SIZE)
        self.assertAlmostEqual(subject_height_fraction(out), 0.86, delta=0.02)

    def test_keeps_subject_centered(self):
        """放大后主体水平中心仍必须在 0.5±0.02（否则构图检查会失败）。"""
        self.assertAlmostEqual(subject_center_x(frame_plate.reframe(synthetic(0.60), 0.86, SIZE)), 0.5, delta=0.02)

    def test_offset_subject_stays_centered(self):
        """主体原本偏一点（真实底板 cx=0.5030）时也要被拉回中间，不能裁掉一侧。"""
        img = synthetic(0.62, offset_x=20)
        before = subject_center_x(img)
        after = subject_center_x(frame_plate.reframe(img, 0.86, SIZE))
        self.assertGreater(before, 0.5)
        self.assertAlmostEqual(after, 0.5, delta=0.02)

    def test_is_mirror_equivariant(self):
        """reframe 必须与水平镜像可交换：否则 turn 的首尾帧不再是严格镜像（§6.3 硬要求）。"""
        img = synthetic(0.60, offset_x=24)
        a = np.asarray(frame_plate.reframe(img.transpose(Image.FLIP_LEFT_RIGHT), 0.86, SIZE))
        b = np.asarray(frame_plate.reframe(img, 0.86, SIZE))[:, ::-1, :]
        self.assertTrue(np.array_equal(a, b), "reframe 与镜像不可交换")

    def test_never_crops_subject(self):
        """放大不得切掉主体：放大后外接框四周仍要有余量。"""
        img = synthetic(0.60)
        out = np.asarray(frame_plate.reframe(img, 0.88, SIZE)).astype(np.int16)
        bg = frame_plate.background_mask(out)
        ys, xs = np.where(~bg)
        self.assertGreater(ys.min(), 0)
        self.assertLess(ys.max(), SIZE[1] - 1)
        self.assertGreater(xs.min(), 0)
        self.assertLess(xs.max(), SIZE[0] - 1)

    def _square_ratio(self, img, size=SIZE, fit=0.865):
        out = np.asarray(frame_plate.reframe(img, fit, size)).astype(int)
        white = (out[..., 0] > 200) & (out[..., 1] > 200) & (out[..., 2] > 200)
        ys, xs = np.where(white)
        self.assertTrue(len(ys) > 100, "找不到正方形标记")
        return (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)

    def test_no_stretch_when_horizontal_padding_is_clamped(self):
        """水平留白被夹时**不得拉成非等比**：正确做法是反过来缩小 crop_h（宁可少放大）。

        做法：主体里画一个正方形标记，reframe 后它必须还是正方形。
        旧实现在这里把 120×120 的标记拉成 134×195（宽高比 0.687，横向压扁 31%）。
        """
        img = Image.new("RGB", SIZE, GREEN)
        w, h, x, y = 700, 600, 200, 170          # 横向留白仅 200 → 16:9 下装不下想要的高度
        img.paste(Image.new("RGB", (w, h), (190, 110, 40)), (x, y))
        img.paste(Image.new("RGB", (120, 120), (255, 255, 255)), (x + (w - 120) // 2, y + (h - 120) // 2))
        self.assertAlmostEqual(self._square_ratio(img), 1.0, delta=0.03, msg="正方形被横向拉伸")

    def test_no_stretch_in_degenerate_wide_subject(self):
        """退化情形（主体极宽、对称 16:9 窗口不存在）也必须**不拉伸**、**不切主体**。

        此时放弃放大：退到画幅内最大的 16:9 窗口。等比是硬约束，宁可不放大。
        """
        img = Image.new("RGB", SIZE, GREEN)
        w, h, x, y = 1500, 500, 10, 220
        img.paste(Image.new("RGB", (w, h), (190, 110, 40)), (x, y))
        img.paste(Image.new("RGB", (120, 120), (255, 255, 255)), (x + (w - 120) // 2, y + (h - 120) // 2))
        self.assertAlmostEqual(self._square_ratio(img), 1.0, delta=0.03, msg="退化情形下画面被拉伸")

    def test_symmetric_pads_are_not_equal_by_construction(self):
        """文档措辞纠偏：上下与左右留白**本来就不同**（左右由 16:9 反推），
        这一条把该事实钉住，避免注释再次写成「四周各留相同像素」。"""
        img = synthetic(0.60)
        rgb = np.asarray(img).astype(np.int16)
        bg = frame_plate.background_mask(rgb)
        ys, xs = np.where(~bg)
        bw, bh = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        # 手工复算 reframe 的留白
        pad_y = int(round(bh * (1.0 / 0.865 - 1.0) / 2.0))
        pad_y = min(pad_y, int(ys.min()), int(SIZE[1] - 1 - ys.max()))
        crop_h = bh + 2 * pad_y
        pad_x = int(round((crop_h * frame_plate.TARGET_ASPECT - bw) / 2.0))
        self.assertNotAlmostEqual(pad_x, pad_y, delta=1, msg="左右与上下留白不应相等")

    def test_fail_closed_without_green(self):
        """没有绿幕像素必须报错，不能静默产出错底板。"""
        with self.assertRaises(RuntimeError):
            frame_plate.reframe(Image.new("RGB", SIZE, (200, 200, 200)), 0.86, SIZE)

    def test_height_already_at_target_is_noop_size(self):
        """本来就是目标高度时不得放大失真（尺寸与构图保持）。"""
        out = frame_plate.reframe(synthetic(0.86), 0.86, SIZE)
        self.assertEqual(out.size, SIZE)
        self.assertAlmostEqual(subject_height_fraction(out), 0.86, delta=0.02)


if __name__ == "__main__":
    unittest.main()
