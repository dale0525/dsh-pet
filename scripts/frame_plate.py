"""把图像模型产出的绿幕图装配成管线需要的 16:9 绿幕底板（frame plate）。

为什么需要这一步（实测事实）：
- 网关的「图生图」**保持输入宽高比**：输入 `test/pet1/target-dog.png` 是 390×520（3:4），
  请求里写 `size=16:9` **被忽略**，产出仍是 3:4（1086×1448）。
- 而下游链路全是 16:9：H3 输出 864×480、`chroma_step02.py` 1280×720。
  参考帧若是 3:4，构图与安全区都无法与视频对齐。

做法：**不触碰主体像素**——只按实测背景中位色在左右补纯色块凑成 16:9，
再整图 lanczos 缩放到统一尺寸（默认 1672×941，与已验证过的 `test/pet1/frames/` 一致）。
补色取背景中位色而非写死 #00FF00，是为了让补出来的区域与模型产出的绿幕**同色**，
避免底板出现两种绿导致「绿幕平坦度」检查失败。

用法：
    python scripts/frame_plate.py out/*.png --out plates/
    python scripts/frame_plate.py img.png --out plates/ --size 1672x941
    python scripts/frame_plate.py plate.png --out plates/ --fit-height 0.865   # 再放大主体

`--fit-height` 的来由（实测，见规格 §16）：H3 成片的「抠像前景占比」比底板低 20–26%
（h264 压缩把毛发边缘压成可判绿的像素），而 §7.2 要求成片前景 ≥ 0.15。
底板主体 0.819 高度占比时成片前景只有 0.149–0.162（贴阈值）；
放大到 ~0.865 后成片前景回到 0.16–0.18，留出余量。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

# 与评估器/抠像链一致的绿幕判定：绿色通道足够亮，且明显压过红蓝。
GREEN_MIN = 100
GREEN_DOMINANCE = 40
TARGET_ASPECT = 16 / 9
DEFAULT_SIZE = (1672, 941)


def background_mask(rgb: np.ndarray) -> np.ndarray:
    """绿幕像素掩码（rgb 为 H×W×3 int16）。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (g > GREEN_MIN) & ((g - np.maximum(r, b)) > GREEN_DOMINANCE)


def plate(src: Path, dst: Path, size: tuple[int, int]) -> dict:
    """单张图 → 16:9 底板。返回可打印的实测摘要。"""
    image = Image.open(src).convert("RGB")
    rgb = np.asarray(image).astype(np.int16)
    mask = background_mask(rgb)
    if not mask.any():
        raise RuntimeError(f"{src.name}: 找不到任何绿幕像素，拒绝装配（fail-closed）")

    # 背景中位色：比均值抗离群点（毛发边缘的绿溢像素不会被算进来）
    fill = tuple(int(np.median(rgb[..., c][mask])) for c in range(3))

    w, h = image.size
    target_w = max(w, round(h * TARGET_ASPECT))
    if target_w > w:
        canvas = Image.new("RGB", (target_w, h), fill)
        canvas.paste(image, ((target_w - w) // 2, 0))
        image = canvas

    image = image.resize(size, Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    image.save(dst)

    out = np.asarray(image).astype(np.int16)
    out_bg = background_mask(out)
    ys, xs = np.where(~out_bg)
    return {
        "src": str(src),
        "dst": str(dst),
        "fill": "#%02X%02X%02X" % fill,
        "padded_px": target_w - w,
        "size": f"{size[0]}x{size[1]}",
        "bg_fraction": round(float(out_bg.mean()), 4) if out_bg.any() else 0.0,
        "center_x": round(float((xs.min() + xs.max()) / 2 / size[0]), 4) if len(xs) else None,
        "height_fraction": round(float((ys.max() - ys.min() + 1) / size[1]), 4) if len(ys) else None,
    }


def reframe(image: Image.Image, fit_height: float, size: tuple[int, int]) -> Image.Image:
    """把主体放大到 `fit_height` 的高度占比（保持 16:9、水平居中、不切主体、不拉伸）。

    做法：裁剪窗口 = **主体外接框在每个轴上左右/上下对称地补留白**——
    上下各 `pad_y`、左右各 `pad_x`（**两者不相等**：pad_y 由 `fit_height` 决定，
    pad_x 由 16:9 反推）。再整块缩放到 `size`。

    **不按「中心坐标 + 半径」算窗口**——那种写法要做整数取整，取整不是镜像对称的
    （会差 1 像素），而 `turn` 类动作的首尾帧必须严格互为镜像（规格 §6.3）。
    这里 `pad_x/pad_y` 只由外接框尺寸与画幅决定，外接框在镜像下精确互换，所以

        reframe(mirror(x)) == mirror(reframe(x))

    逐像素成立（已用 60 例随机主体 + 贴边/超目标等边界独立复算）。

    **16:9 是硬约束，不能靠夹取留白后硬 resize 来"凑"**：
    若水平留白不够（主体很宽或贴左右边），旧实现只夹 `pad_x` 而不改 `crop_h`，
    裁剪框宽高比就小于 16:9，再 resize 到 `size` 会把画面**横向拉扁**
    （实测：主体内一个 120×120 的正方形标记被拉成 134×195，宽高比 0.687）。
    现在的做法是**在水平留白受限时反过来缩小 `crop_h`**，始终保持 `crop_w ≈ 16/9 · crop_h`，
    代价是主体放大得少一些（宁可少放大，也绝不切主体、绝不拉伸）。

    **已知边界**：留白不能超出画幅，所以当主体本身贴着画幅上下边时达不到请求的 `fit_height`
    （极端情况主体高度占比 1.0）。这是刻意取舍。调用方据此需要知道：
      - `main()` 会打印**实测**高度占比（`| fit-height 0.865 -> h=0.866`），据此判断是否达标；
      - 若真没达到，下游 §7.1 门禁（高度占比 ∈ [0.70, 0.90]）会显式失败——失败是**响亮**的。
    """
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    bg = background_mask(rgb)
    if not bg.any():
        raise RuntimeError("找不到任何绿幕像素，拒绝 reframe（fail-closed）")
    ys, xs = np.where(~bg)
    if len(ys) == 0:
        raise RuntimeError("画面里只有绿幕、没有主体，拒绝 reframe（fail-closed）")

    w, h = image.size
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw, bh = x1 - x0 + 1, y1 - y0 + 1

    # 两个轴上「对称可用」的最大留白（取两侧较小值，保证裁剪框仍在画幅内且不缺主体）
    max_px = min(x0, w - 1 - x1)
    max_py = min(y0, h - 1 - y1)

    # 裁剪高 h 必须同时满足：① 由 fit_height 反推的期望值；② 装得下主体（h ≥ bh 且 16:9 下 h ≥ bw/A）；
    # ③ 不越出画幅（h ≤ bh + 2·max_py 且 h ≤ (bw + 2·max_px)/A）。
    # 取 [lo, hi] 内最接近期望值的可行解 —— 这样 16:9 与「不切主体」同时成立，绝不需要靠 resize 硬拉。
    want_h = bh + 2 * max(0, int(round(bh * (1.0 / fit_height - 1.0) / 2.0)))
    lo = max(float(bh), bw / TARGET_ASPECT)
    hi = min(float(want_h), bh + 2 * max_py, (bw + 2 * max_px) / TARGET_ASPECT)
    if lo <= hi:
        crop_h = min(max(float(want_h), lo), hi)
        crop_w = crop_h * TARGET_ASPECT
        # 整数化：左右/上下留白各自对称取整，保证镜像下逐像素可交换
        pad_x = max(0, min((int(round(crop_w)) - bw) // 2, max_px))
        pad_y = max(0, min((int(round(crop_h)) - bh) // 2, max_py))
    else:
        # 理论上只在「主体横跨整幅且紧贴上下边」时才不可行（`plate()` 产出的底板不会这样）。
        # 退到画幅内**最大的 16:9 窗口**：等比是硬约束——宁可不放大，也绝不拉伸、绝不切主体。
        ch = h
        cw = int(round(h * TARGET_ASPECT))
        if cw > w:
            cw, ch = w, int(round(w / TARGET_ASPECT))
        left = max(0, min(max(0, min(x0, w - cw)), max(0, x1 - cw + 1)))
        top = max(0, min(max(0, min(y0, h - ch)), max(0, y1 - ch + 1)))
        return image.crop((left, top, left + cw, top + ch)).resize(size, Image.LANCZOS)

    top, left = y0 - pad_y, x0 - pad_x
    return image.crop((left, top, left + bw + 2 * pad_x, top + bh + 2 * pad_y)).resize(size, Image.LANCZOS)

    left, top = x0 - pad_x, y0 - pad_y
    return image.crop((left, top, left + crop_w, top + crop_h)).resize(size, Image.LANCZOS)


def parse_size(value: str) -> tuple[int, int]:
    w, _, h = value.lower().partition("x")
    return int(w), int(h)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="底板输出目录")
    ap.add_argument("--size", type=parse_size, default=DEFAULT_SIZE, help="底板尺寸，默认 1672x941")
    ap.add_argument("--fit-height", type=float, default=None,
                    help="装配后再把主体放大到该高度占比（如 0.865）；不给则原样输出")
    args = ap.parse_args()

    for src in args.images:
        dst = args.out / src.name
        info = plate(src, dst, args.size)
        line = (
            f"{src.name} -> {info['dst']} fill={info['fill']} "
            f"pad={info['padded_px']}px bg={info['bg_fraction']} "
            f"cx={info['center_x']} h={info['height_fraction']}"
        )
        if args.fit_height is not None:
            reframed = reframe(Image.open(dst), args.fit_height, args.size)
            arr = np.asarray(reframed).astype(np.int16)
            bg = background_mask(arr)
            ys, xs = np.where(~bg)
            reframed.save(dst)
            line += (
                f" | fit-height {args.fit_height} -> h={round((ys.max() - ys.min() + 1) / args.size[1], 4)}"
                f" cx={round((xs.min() + xs.max()) / 2 / args.size[0], 4)}"
                f" bg={round(float(bg.mean()), 4)}"
            )
        print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
