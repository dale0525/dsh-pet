#!/usr/bin/env python3
"""Acceptance evaluator for dachshund green screen and deliverable assets.

Evaluates frame assets against §7.1 and video assets against §7.2 / §7.4,
incorporating user clarifications and ruled criteria (§16.8, §16.9).

Video evaluation supports two modes:
1. Raw Mode (H3 green-screen clip, e.g. output.mp4):
   - Container checks: 864x480, 24fps, duration = requested +/-0.05s, codec h264.
   - 5-point green matte background fraction >= 0.70.
   - Chroma keying: standing sampling points (t=0, t=9.9) foreground >= 0.15 (decisive).
     5-point min foreground is reported as reference value.
   - Green spill: if deliverable counterpart is available, visible green edge <= 2%
     is decisive (ruled 2026-09-02); raw spill is reported as reference.
     If no deliverable is available, raw spill <= 2% is used.
   - Geometry: start/end consistency <= 5%, zero displacement <= 0.08.

2. Keyed Mode (deliverable VP9+alpha webm, e.g. step04/*.webm):
   - Container checks: 640x360, 24fps, duration = requested +/-0.05s, codec vp9.
   - 5-point transparent matte background fraction >= 0.70.
   - Chroma keying: standing sampling points (t=0, t=9.9) foreground >= 0.15 (decisive,
     measured on counterpart raw video if present, or keyed alpha). 5-point min fg as reference.
   - Green spill: visible green edge fraction on deliverable (alpha > 128, g-r > 25, g-b > 25) <= 2%
     (ruled 2026-09-02); raw spill is reported as reference.
   - Geometry: start/end consistency <= 5%, zero displacement <= 0.08.

Mode selection:
   Automatic based on file extension (.webm -> keyed, .mp4 -> raw), or explicitly
   specified via --keyed / --raw flags.

Usage:
    python evaluate_dachshund.py frames <img.png ...> [--json out.json]
    python evaluate_dachshund.py video <file.mp4|file.webm> --seconds <sec> [--keyed|--raw] [--deliverable <path>] [--raw-video <path>] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops

REPO_ROOT = Path(__file__).resolve().parents[2]
PET_DIR = Path(__file__).resolve().parent  # pets/dachshund/
H3_DIR = PET_DIR / "h3"  # 本 pet pack 的 H3 成片（扁平、按动作名命名）
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "test" / "pet1"))

from _tools import ffmpeg, ffprobe  # noqa: E402

try:
    import evaluate_h3_pet1 as pet1_ev  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - 环境缺失路径
    # 规格 §13.6 5.1 裁定「复用/扩展现有 test/pet1/ 的评估器」，而 test/pet1/ 按 §11 裁定 5
    # 不入版本库——干净克隆里没有它。这里不静默降级（门禁宁可报错，也不假装通过），
    # 只把「缺什么、怎么补」说清楚。
    raise SystemExit(
        "无法复用 test/pet1/evaluate_h3_pet1.py 的度量原语。\n"
        f"  期望路径: {REPO_ROOT / 'test' / 'pet1' / 'evaluate_h3_pet1.py'}\n"
        "  原因: test/pet1/ 按规格 §11 裁定 5 不纳入 git，需从产出它的那次会话/机器取得。\n"
        "  补救: 放回 test/pet1/（至少 evaluate_h3_pet1.py、frames/、h3-out/output.mp4）后重跑。"
    ) from exc

# Re-export / alias primitives from pet1 evaluator
green_matte_stats = pet1_ev.green_matte_stats
green_spill_fraction = pet1_ev.green_spill_fraction
MIN_SUBJECT_FRACTION = pet1_ev.MIN_SUBJECT_FRACTION

# §7.1 / §7.2 Thresholds
EXPECT_W, EXPECT_H, EXPECT_FPS = 864, 480, 24
GREEN_HUE_MIN = 70.0
GREEN_HUE_MAX = 170.0
SAT_MIN = 0.15
VAL_MIN = 0.15


def silhouette_profile(image: Image.Image) -> dict:
    """Geometry of the subject, expressed as frame fractions.

    Supports both keyed RGBA (alpha channel) and green-screen RGB.
    """
    if "A" in image.getbands():
        mask = image.getchannel("A").point(lambda a: 255 if a > 128 else 0)
        box = mask.getbbox()
    else:
        rgb = image.convert("RGB")
        box = ImageChops.invert(pet1_ev._chroma_key(rgb)).getbbox()
    if box is None:
        return {"error": "no foreground detected"}
    width, height = image.size
    x1, y1, x2, y2 = box
    return {
        "width_fraction": round((x2 - x1) / width, 4),
        "height_fraction": round((y2 - y1) / height, 4),
        "center_x_fraction": round((x1 + x2) / 2 / width, 4),
        "top_fraction": round(y1 / height, 4),
        "bottom_fraction": round(y2 / height, 4),
    }


def matte_stats(image: Image.Image) -> dict:
    """Matte statistics for either keyed RGBA or green-screen RGB."""
    if "A" in image.getbands():
        arr_a = np.array(image.getchannel("A"), dtype=np.uint8)
        bg_px = int(np.count_nonzero(arr_a <= 128))
        total = arr_a.size
        bg_frac = round(bg_px / total, 4)
        fg_frac = round(1.0 - bg_frac, 4)
        return {
            "background_fraction": bg_frac,
            "foreground_fraction": fg_frac,
            "background_mean_rgb": [0.0, 0.0, 0.0],
            "background_stddev": [0.0, 0.0, 0.0],
        }
    return green_matte_stats(image)


def deliverable_green_spill_fraction(image: Image.Image) -> float:
    """Compute deliverable visible green edge spill fraction according to §16.8 / §16.9.

    Definition (ruled 2026-09-02):
        In pixels where alpha > 128, fraction of pixels satisfying
        (g - r > 25) and (g - b > 25).
    """
    img = image.convert("RGBA")
    arr = np.array(img, dtype=np.int16)
    r = arr[..., 0]
    g = arr[..., 1]
    b = arr[..., 2]
    a = arr[..., 3]
    subject_mask = a > 128
    subject_px = int(np.count_nonzero(subject_mask))
    if subject_px == 0:
        return 0.0
    spill_mask = subject_mask & ((g - r) > 25) & ((g - b) > 25)
    spill_px = int(np.count_nonzero(spill_mask))
    return round(spill_px / subject_px, 5)


def resolve_raw_counterpart(video_path: Path) -> Path | None:
    """Find corresponding raw H3 video (h264 mp4) if present in the repo.

    `pets/dachshund/h3/` 是扁平存放、以动作名命名的 H3 成片（唯一事实来源）；
    早先按 p2/p3/p4 分批、`<动作>/output.mp4` 嵌套的布局已合并到这里。
    """
    stem = video_path.stem
    candidates = [
        H3_DIR / f"{stem}.mp4",
        REPO_ROOT / "step01" / f"{stem}.mp4",
        video_path.with_suffix(".mp4"),
        video_path.parent / f"{stem}.mp4",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def resolve_keyed_counterpart(video_path: Path) -> Path | None:
    """Find corresponding keyed deliverable (VP9+alpha webm) if present in the repo.

    `step04/` 是 `encode_thumbs.py` 的契约输出目录（gitignore 本地再生，不随仓库分发），
    故这里只做「在则用」的探测，缺失是正常状态。
    """
    stem = video_path.stem
    candidates = [
        REPO_ROOT / "step04" / f"{stem}.webm",
        video_path.with_suffix(".webm"),
        video_path.parent / f"{stem}.webm",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def chroma_key_fractions(image: Image.Image) -> dict[str, float]:
    """Compute chroma key background and foreground fractions according to scripts/chroma_step02.py.

    HSV threshold: Hue in [70.0, 170.0], Saturation >= 0.15, Value >= 0.15.
    """
    arr = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    delta = mx - mn
    nz = delta > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        hr = 60.0 * (((g - b) / np.where(nz, delta, 1.0)) % 6.0)
        hg = 60.0 * (((b - r) / np.where(nz, delta, 1.0)) + 2.0)
        hb = 60.0 * (((r - g) / np.where(nz, delta, 1.0)) + 4.0)
    hue = np.where((mx == r) & nz, hr, np.where((mx == g) & nz, hg, np.where((mx == b) & nz, hb, 0.0)))
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-6), 0.0)
    val = mx
    bg_mask = (hue >= GREEN_HUE_MIN) & (hue <= GREEN_HUE_MAX) & (sat >= SAT_MIN) & (val >= VAL_MIN)
    total = bg_mask.size
    bg_px = int(np.count_nonzero(bg_mask))
    bg_fraction = round(bg_px / total, 4)
    fg_fraction = round(1.0 - bg_fraction, 4)
    return {
        "background_fraction": bg_fraction,
        "foreground_fraction": fg_fraction,
    }


def _has_detected_subject(matte: dict, profile: dict) -> bool:
    if "error" in profile:
        return False
    fg_frac = matte.get("foreground_fraction", 0.0)
    return fg_frac >= MIN_SUBJECT_FRACTION


def probe_video(video_path: Path | str) -> dict:
    cmd = [
        ffprobe(), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path),
    ]
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {done.stderr.strip()[:400]}")
    return json.loads(done.stdout)


def extract_frame(
    video_path: Path | str,
    seconds: float,
    out_path: Path,
    keyed: bool = False,
) -> bool:
    cmd = [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    if keyed:
        cmd.extend(["-c:v", "libvpx-vp9"])
    cmd.extend(["-ss", f"{seconds:.3f}", "-i", str(video_path)])
    if keyed:
        cmd.extend(["-pix_fmt", "rgba"])
    cmd.extend(["-frames:v", "1", str(out_path)])
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return done.returncode == 0 and out_path.is_file()



def evaluate_frame(image_or_path: Image.Image | Path | str) -> dict:
    """Evaluate a single opening/ending frame against §7.1."""
    if isinstance(image_or_path, (str, Path)):
        frame_path = str(image_or_path)
        img = Image.open(image_or_path).convert("RGB")
    else:
        frame_path = "<in_memory_image>"
        img = image_or_path.convert("RGB")

    matte = green_matte_stats(img)
    profile = silhouette_profile(img)
    subject_detected = _has_detected_subject(matte, profile)

    # 1. 绿幕（背景）占比 >= 0.70
    bg_frac = matte["background_fraction"]
    bg_frac_passed = bg_frac >= 0.70

    # 2. 绿幕均值接近 (0,255,0) 且各通道偏差 <= 25
    mean_rgb = matte["background_mean_rgb"]
    dev_r = abs(mean_rgb[0] - 0.0)
    dev_g = abs(mean_rgb[1] - 255.0)
    dev_b = abs(mean_rgb[2] - 0.0)
    mean_passed = max(dev_r, dev_g, dev_b) <= 25.0

    # 3. 绿幕平坦度（标准差 <= 15）
    std_rgb = matte["background_stddev"]
    std_passed = max(std_rgb) <= 15.0

    # 4. 构图 - 主体水平中心 in [0.40, 0.60] (fail-closed)
    if subject_detected:
        center_x = profile["center_x_fraction"]
        center_passed = (0.40 <= center_x <= 0.60)
    else:
        center_x = None
        center_passed = False

    # 5. 构图 - 主体高度占比 in [0.70, 0.90] (fail-closed)
    if subject_detected:
        height_frac = profile["height_fraction"]
        height_passed = (0.70 <= height_frac <= 0.90)
    else:
        height_frac = None
        height_passed = False

    checks: dict[str, dict[str, Any]] = {
        "green_background_fraction": {
            "passed": bg_frac_passed,
            "measured": bg_frac,
            "threshold": ">= 0.70",
        },
        "green_background_mean": {
            "passed": mean_passed,
            "measured": mean_rgb,
            "threshold": "abs(mean - (0,255,0)) <= 25 per channel",
        },
        "green_background_stddev": {
            "passed": std_passed,
            "measured": std_rgb,
            "threshold": "<= 15.0 per channel",
        },
        "subject_center_x": {
            "passed": center_passed,
            "measured": center_x,
            "threshold": "[0.40, 0.60]",
        },
        "subject_height_fraction": {
            "passed": height_passed,
            "measured": height_frac,
            "threshold": "[0.70, 0.90]",
        },
        "identity_consistency": {
            "passed": None,
            "status": "MANUAL_VISUAL_REVIEW",
            "threshold": "毛色/耳型/体型与 target-dog.png 相符（人工目视）",
            "measured": "PENDING_VISUAL_INSPECTION",
        },
        "no_props": {
            "passed": None,
            "status": "MANUAL_VISUAL_REVIEW",
            "threshold": "首帧无任何非狗非绿幕物体（人工目视）",
            "measured": "PENDING_VISUAL_INSPECTION",
        },
    }

    quantitative_passed = [
        name for name, c in checks.items()
        if c.get("status") != "MANUAL_VISUAL_REVIEW" and c["passed"] is True
    ]
    quantitative_failed = [
        name for name, c in checks.items()
        if c.get("status") != "MANUAL_VISUAL_REVIEW" and c["passed"] is False
    ]

    # Verdict determination:
    # If all quantitative checks pass -> PASS
    # If background checks fail -> FAIL
    # If background checks pass but subject missing/out of bounds -> REVIEW (fail-closed)
    if not quantitative_failed:
        verdict = "PASS"
    elif not bg_frac_passed or not mean_passed or not std_passed:
        verdict = "FAIL"
    else:
        verdict = "REVIEW"

    return {
        "frame": frame_path,
        "verdict": verdict,
        "checks": checks,
        "passed": quantitative_passed,
        "failed": quantitative_failed,
    }


def evaluate_frames(frame_paths: list[Path | str]) -> dict:
    """Evaluate a collection of frames against §7.1."""
    frames_report = {}
    verdicts = []
    for fp in frame_paths:
        p = Path(fp)
        rep = evaluate_frame(p)
        frames_report[str(p)] = rep
        verdicts.append(rep["verdict"])

    if any(v == "FAIL" for v in verdicts):
        overall_verdict = "FAIL"
    elif any(v == "REVIEW" for v in verdicts):
        overall_verdict = "REVIEW"
    elif verdicts:
        overall_verdict = "PASS"
    else:
        overall_verdict = "REVIEW"

    return {
        "mode": "frames",
        "verdict": overall_verdict,
        "frames": frames_report,
        "total_frames": len(frame_paths),
    }


def evaluate_video(
    video_path: Path | str,
    expected_seconds: float,
    keyed: bool | None = None,
    deliverable_path: Path | str | None = None,
    raw_video_path: Path | str | None = None,
) -> dict:
    """Evaluate a video against §7.2 / §7.4 and ruled criteria (§16.8, §16.9).

    Supports two modes:
    1. Raw mode (H3 green screen clip, e.g. output.mp4):
       - Container checks: 864x480, 24fps, duration = expected +/-0.05s, codec h264.
       - 5-point green matte background fraction >= 0.70.
       - Chroma keying decision: standing sampling points (t=0, t=9.9) foreground >= 0.15.
         5-point min foreground is recorded as reference value.
       - Green spill: if deliverable counterpart is present, decision is based on
         deliverable spill <= 2% (ruled 2026-09-02); raw spill is recorded as reference.
       - Geometry: start/end consistency <= 5%, zero displacement <= 0.08.

    2. Keyed mode (deliverable VP9+alpha webm, e.g. step04/*.webm):
       - Container checks: 640x360, 24fps, duration = expected +/-0.05s, codec vp9.
       - 5-point transparent matte background fraction >= 0.70.
       - Chroma keying decision: standing sampling points (t=0, t=9.9) foreground >= 0.15
         (measured on counterpart raw video if present, or keyed alpha). 5-point min fg as reference.
       - Green spill: visible green edge fraction on deliverable (alpha > 128, g-r > 25, g-b > 25) <= 2%
         (ruled 2026-09-02); raw spill is recorded as reference.
       - Geometry: start/end consistency <= 5%, zero displacement <= 0.08.
    """
    video = Path(video_path)
    info = probe_video(video)
    streams = info.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video_stream is None:
        raise ValueError(f"Video file has no video stream: {video}")

    width = int(video_stream["width"])
    height = int(video_stream["height"])
    r_frame_rate = video_stream.get("r_frame_rate", "")
    try:
        num, den = map(int, r_frame_rate.split("/"))
        fps_val = round(num / den, 2)
    except Exception:
        fps_val = 0.0

    duration_val = round(float(info["format"]["duration"]), 3)
    video_codec = video_stream.get("codec_name", "")

    # Mode determination:
    if keyed is not None:
        is_keyed = keyed
    elif video.suffix.lower() == ".webm":
        is_keyed = True
    elif video_codec == "vp9":
        is_keyed = True
    elif video_stream.get("tags", {}).get("ALPHA_MODE") == "1":
        is_keyed = True
    else:
        is_keyed = False

    # Container contract checks
    if is_keyed:
        expect_w, expect_h = 640, 360
        codec_passed = video_codec == "vp9"
        codec_threshold = "vp9"
        res_threshold = "640x360"
    else:
        expect_w, expect_h = EXPECT_W, EXPECT_H
        codec_passed = video_codec in ("h264", "libx264")
        codec_threshold = "h264"
        res_threshold = f"{EXPECT_W}x{EXPECT_H}"

    res_passed = (width, height) == (expect_w, expect_h)
    fps_passed = (r_frame_rate == f"{EXPECT_FPS}/1") or (abs(fps_val - EXPECT_FPS) < 0.1)
    duration_passed = abs(duration_val - expected_seconds) <= 0.05

    container_checks = {
        "container_resolution": {
            "passed": res_passed,
            "measured": f"{width}x{height}",
            "threshold": res_threshold,
        },
        "container_fps": {
            "passed": fps_passed,
            "measured": fps_val,
            "threshold": f"{EXPECT_FPS}fps ({EXPECT_FPS}/1)",
        },
        "container_duration": {
            "passed": duration_passed,
            "measured": duration_val,
            "threshold": f"{expected_seconds:.2f}s +/- 0.05s",
        },
        "container_codec": {
            "passed": codec_passed,
            "measured": video_codec,
            "threshold": codec_threshold,
        },
    }
    container_passed = all(c["passed"] for c in container_checks.values())

    # Resolve counterparts
    if is_keyed:
        keyed_video = video
        raw_video = Path(raw_video_path) if raw_video_path else resolve_raw_counterpart(video)
    else:
        raw_video = video
        keyed_video = Path(deliverable_path) if deliverable_path else resolve_keyed_counterpart(video)

    # 5-point sampling (0, 25, 50, 75, 95%)
    fractions = [0.0, 0.25, 0.50, 0.75, 0.95]
    sample_frames: list[Image.Image] = []

    with tempfile.TemporaryDirectory(prefix="dachshund-video-eval-") as tmp:
        tmp_dir = Path(tmp)
        for i, frac in enumerate(fractions):
            t = expected_seconds * frac
            if duration_val > 0.1:
                t = min(t, max(0.0, duration_val - 1.0 / (fps_val or EXPECT_FPS)))
            out_png = tmp_dir / f"sample_{i:02d}.png"
            if extract_frame(video, t, out_png, keyed=is_keyed):
                sample_frames.append(Image.open(out_png))

        extraction_ok = len(sample_frames) == len(fractions)

        mattes = [matte_stats(img) for img in sample_frames]
        profiles = [silhouette_profile(img) for img in sample_frames]
        has_subjects = [
            _has_detected_subject(m, p) for m, p in zip(mattes, profiles)
        ]

        # Determine deliverable spill and raw spill:
        max_deliverable_spill: float | None = None
        max_raw_spill: float | None = None
        raw_samples: list[Image.Image] = []

        if is_keyed:
            deliverable_spills = [deliverable_green_spill_fraction(img) for img in sample_frames]
            max_deliverable_spill = max(deliverable_spills) if deliverable_spills else 0.0

            if raw_video and raw_video.is_file():
                for i, frac in enumerate(fractions):
                    t = expected_seconds * frac
                    out_raw = tmp_dir / f"raw_sample_{i:02d}.png"
                    if extract_frame(raw_video, t, out_raw, keyed=False):
                        raw_samples.append(Image.open(out_raw).convert("RGB"))
                if raw_samples:
                    max_raw_spill = max(green_spill_fraction(img) for img in raw_samples)
        else:
            raw_spills = [green_spill_fraction(img.convert("RGB")) for img in sample_frames]
            max_raw_spill = max(raw_spills) if raw_spills else 0.0

            if keyed_video and keyed_video.is_file():
                deliv_samples = []
                for i, frac in enumerate(fractions):
                    t = expected_seconds * frac
                    out_deliv = tmp_dir / f"deliv_sample_{i:02d}.png"
                    if extract_frame(keyed_video, t, out_deliv, keyed=True):
                        deliv_samples.append(Image.open(out_deliv))
                if deliv_samples:
                    max_deliverable_spill = max(deliverable_green_spill_fraction(img) for img in deliv_samples)

        # Standing points foreground (t=0, t=9.9) and 5-point min foreground:
        # Prefer raw video for chroma keying foreground metrics when available
        standing_video = raw_video if (raw_video and raw_video.is_file()) else video
        standing_is_keyed = (standing_video == keyed_video) if keyed_video else is_keyed

        t_start = 0.0
        if expected_seconds >= 10.0:
            t_end = min(9.9, max(0.0, duration_val - 1.0 / (fps_val or EXPECT_FPS)))
        else:
            t_end = max(0.0, min(expected_seconds * 0.95, duration_val - 1.0 / (fps_val or EXPECT_FPS)))

        out_t0 = tmp_dir / "standing_t0.png"
        out_tend = tmp_dir / "standing_tend.png"
        got_t0 = extract_frame(standing_video, t_start, out_t0, keyed=standing_is_keyed)
        got_tend = extract_frame(standing_video, t_end, out_tend, keyed=standing_is_keyed)

        if got_t0 and got_tend:
            img_t0 = Image.open(out_t0)
            img_tend = Image.open(out_tend)
            if standing_is_keyed:
                fg_start = matte_stats(img_t0)["foreground_fraction"]
                fg_end = matte_stats(img_tend)["foreground_fraction"]
            else:
                fg_start = chroma_key_fractions(img_t0)["foreground_fraction"]
                fg_end = chroma_key_fractions(img_tend)["foreground_fraction"]
        else:
            fg_start = 0.0
            fg_end = 0.0

        min_standing_fg = min(fg_start, fg_end)
        standing_decision = {
            "t0": fg_start,
            "t9_9": fg_end,
            "min_standing": min_standing_fg,
        }

        # 5-point foreground reference:
        if not standing_is_keyed:
            frames_for_chroma = sample_frames if standing_video == video else raw_samples
            chromas = [chroma_key_fractions(img) for img in frames_for_chroma]
            min_chroma_bg = min(c["background_fraction"] for c in chromas) if chromas else 0.0
            min_5point_fg = min(c["foreground_fraction"] for c in chromas) if chromas else 0.0
        else:
            min_chroma_bg = min(m["background_fraction"] for m in mattes) if mattes else 0.0
            min_5point_fg = min(m["foreground_fraction"] for m in mattes) if mattes else 0.0

        # Gate decisions (ruled criteria):
        # 1. 5 点采样每点背景占比 >= 0.70
        bg_fractions = [m["background_fraction"] for m in mattes]
        matte_5pt_passed = extraction_ok and all(b >= 0.70 for b in bg_fractions)

        # 2. 抠像可用：背景 >= 0.70 且站立采样点 (首末) 前景 >= 0.15 (决定值)
        standing_passed = (fg_start >= 0.15) and (fg_end >= 0.15)
        chroma_keyable_passed = extraction_ok and (min_chroma_bg >= 0.70) and standing_passed

        # 3. 绿溢判定：交付物绿溢 <= 2% 为决定值 (若无交付物则使用原始绿溢)
        if max_deliverable_spill is not None:
            spill_passed = extraction_ok and (max_deliverable_spill <= 0.02)
            spill_threshold = "deliverable spill <= 0.02 (ruled 2026-09-02)"
            measured_spill: float | None = max_deliverable_spill
        else:
            spill_passed = extraction_ok and (max_raw_spill is not None and max_raw_spill <= 0.02)
            spill_threshold = "<= 0.02 (2%)"
            measured_spill = max_raw_spill

        # 4. 首尾一致
        if extraction_ok and has_subjects[0] and has_subjects[4]:
            p0 = profiles[0]
            p4 = profiles[4]
            height_diff = round(abs(p0["height_fraction"] - p4["height_fraction"]), 4)
            center_x_diff = round(abs(p0["center_x_fraction"] - p4["center_x_fraction"]), 4)
            start_end_passed = (height_diff <= 0.05) and (center_x_diff <= 0.05)
            start_end_measured: dict[str, Any] = {
                "height_diff": height_diff,
                "center_x_diff": center_x_diff,
            }
        else:
            height_diff = None
            center_x_diff = None
            start_end_passed = False
            start_end_measured = {
                "height_diff": None,
                "center_x_diff": None,
            }

        # 5. 零位移
        if extraction_ok and all(has_subjects):
            centers = [p["center_x_fraction"] for p in profiles]
            displacement_range = round(max(centers) - min(centers), 4)
            zero_disp_passed = displacement_range <= 0.08
            zero_disp_measured: float | None = displacement_range
        else:
            displacement_range = None
            zero_disp_passed = False
            zero_disp_measured = None

    checks: dict[str, dict[str, Any]] = {
        **container_checks,
        "green_matte_5point": {
            "passed": matte_5pt_passed,
            "measured": bg_fractions,
            "threshold": "all 5 samples background_fraction >= 0.70",
        },
        "chroma_keyable": {
            "passed": chroma_keyable_passed,
            "measured": {
                "min_bg_fraction": min_chroma_bg,
                "min_fg_fraction": min_standing_fg,
                "standing_foreground_decision": standing_decision,
                "min_5point_foreground_reference": min_5point_fg,
            },
            "standing_foreground_decision": standing_decision,
            "min_5point_foreground_reference": min_5point_fg,
            "threshold": "bg >= 0.70 and standing foreground >= 0.15 at t=0 and t=9.9 (ruled 2026-09-02)",
        },
        "green_spill": {
            "passed": spill_passed,
            "measured": measured_spill,
            "deliverable_spill_decision": max_deliverable_spill,
            "raw_spill_reference": max_raw_spill,
            "threshold": spill_threshold,
        },
        "start_end_consistency": {
            "passed": start_end_passed,
            "measured": start_end_measured,
            "threshold": "height_diff <= 0.05 and center_x_diff <= 0.05",
        },
        "zero_displacement": {
            "passed": zero_disp_passed,
            "measured": zero_disp_measured,
            "threshold": "5-point center_x range <= 0.08",
        },
    }

    metrics = {
        "deliverable_spill_decision": max_deliverable_spill,
        "raw_spill_reference": max_raw_spill,
        "standing_foreground_decision": standing_decision,
        "min_5point_foreground_reference": min_5point_fg,
        "min_green_matte_fraction": min(bg_fractions) if bg_fractions else 0.0,
        "min_chroma_bg": min_chroma_bg,
        "min_chroma_fg": min_5point_fg,
        "max_green_spill": measured_spill,
        "center_x_range": displacement_range,
        "start_end_height_diff": height_diff,
        "start_end_center_x_diff": center_x_diff,
    }

    all_passed = all(c["passed"] for c in checks.values())

    # §7.4 Gate rules:
    # 1. Container mismatch -> FAIL
    # 2. All checks passed -> PASS
    # 3. Valid container but content/gate checks fail (e.g. dogless pure green) -> REVIEW
    if not container_passed:
        verdict = "FAIL"
    elif all_passed:
        verdict = "PASS"
    else:
        verdict = "REVIEW"

    passed_checks = [k for k, v in checks.items() if v["passed"]]
    failed_checks = [k for k, v in checks.items() if not v["passed"]]

    return {
        "mode": "video",
        "video": str(video),
        "expected_seconds": expected_seconds,
        "verdict": verdict,
        "container": {
            "width": width,
            "height": height,
            "fps": r_frame_rate,
            "duration_seconds": duration_val,
            "video_codec": video_codec,
        },
        "checks": checks,
        "metrics": metrics,
        "passed": passed_checks,
        "failed": failed_checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # frames mode
    p_frames = subparsers.add_parser("frames", help="Evaluate frame images against §7.1")
    p_frames.add_argument("frames", nargs="+", type=Path, help="Paths to frame PNG files")
    p_frames.add_argument("--json", type=Path, help="Output report JSON file path")

    # video mode
    p_video = subparsers.add_parser("video", help="Evaluate video against §7.2 / §7.4")
    p_video.add_argument("video", type=Path, help="Path to video MP4 or WebM file")
    p_video.add_argument("--seconds", type=float, required=True, help="Expected duration in seconds")
    p_video.add_argument("--keyed", action="store_true", default=None, help="Force keyed deliverable mode (VP9+alpha webm)")
    p_video.add_argument("--raw", action="store_true", default=None, help="Force raw green-screen mode (H3 h264 mp4)")
    p_video.add_argument("--deliverable", type=Path, default=None, help="Counterpart keyed deliverable webm path")
    p_video.add_argument("--raw-video", type=Path, default=None, help="Counterpart raw green-screen video path")
    p_video.add_argument("--json", type=Path, help="Output report JSON file path")

    args = parser.parse_args(argv)

    if args.mode == "frames":
        report = evaluate_frames(args.frames)
    elif args.mode == "video":
        if not args.video.is_file():
            print(f"evaluate_dachshund: file not found: {args.video}", file=sys.stderr)
            return 2
        keyed_flag = True if args.keyed else (False if args.raw else None)
        report = evaluate_video(
            args.video,
            expected_seconds=args.seconds,
            keyed=keyed_flag,
            deliverable_path=args.deliverable,
            raw_video_path=args.raw_video,
        )
    else:
        parser.print_help(sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text, encoding="utf-8")

    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
