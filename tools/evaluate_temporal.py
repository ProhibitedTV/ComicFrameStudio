"""Reproduce transport comparisons on generated, redistributable fixtures.

Run: python tools/evaluate_temporal.py --output docs/evidence/temporal.json
These are transport tests with synthetic stylization, not diffusion quality scores.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
from PIL import Image, ImageDraw

from comicframe_optical_flow import OpticalFlowTemporalMixin as Flow, TRANSPORT_VERSION


def legacy_confidence(prev, cur, forward, backward, quality=False):
    """Frozen confidence algorithm from main@5341245, before the fix."""
    h, w = cur.shape
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    mx, my = gx + backward[..., 0], gy + backward[..., 1]
    valid = (mx >= 0) & (mx <= w - 1) & (my >= 0) & (my <= h - 1)
    fx = cv2.remap(
        forward[..., 0], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
    )
    fy = cv2.remap(
        forward[..., 1], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
    )
    error = np.hypot(backward[..., 0] + fx, backward[..., 1] + fy)
    tolerance = (1.0 if quality else 1.5) + 0.06 * np.linalg.norm(backward, axis=2)
    fb = np.exp(-((error / tolerance) ** 2))
    warped = cv2.remap(prev, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
    photo = np.exp(
        -((cv2.absdiff(cur, warped).astype(np.float32) / (24 if quality else 30)) ** 2)
    )
    raw = np.sqrt(np.clip(fb * photo, 0, 1)) * valid
    return cv2.GaussianBlur(raw.astype(np.float32), (0, 0), 1.1 if quality else 1.4)


def fixture(kind: str, count=12, size=(256, 160)):
    """Known horizontal motion, exposed borders, moving occluders, cuts/lighting."""
    w, h = size
    rng = np.random.default_rng(734)
    # Broad shapes plus source detail exercise flow without a uniform-image cheat.
    base = rng.integers(20, 230, (h, w + count * 3, 3), dtype=np.uint8)
    base = cv2.GaussianBlur(base, (0, 0), 1.0)
    cv2.rectangle(base, (32, 35), (100, 125), (45, 160, 210), -1)
    cv2.circle(base, (164, 72), 29, (200, 130, 55), -1)
    cv2.line(base, (20, 140), (250, 28), (35, 50, 90), 3)
    frames, styled, masks = [], [], []
    shift = 0 if kind in {"static", "lighting", "cut"} else 2
    for i in range(count):
        frame = base[:, i * shift : i * shift + w].copy()
        occlusion = np.zeros((h, w), dtype=bool)
        if kind == "occlusion":
            x = 70 + i * 6
            frame[28:134, x : x + 24] = (245, 230, 240)
            # Current occluder and newly revealed old footprint cannot share history.
            occlusion[26:136, max(0, x - 8) : x + 26] = True
        if kind == "lighting" and i >= count // 2:
            frame = np.clip(frame.astype(np.float32) * 0.55, 0, 255).astype(np.uint8)
        if kind == "cut" and i >= count // 2:
            frame = 255 - frame
        art = cv2.bilateralFilter(frame, 5, 55, 4).astype(np.float32)
        art += np.array([8, -5, 6], np.float32) * np.sin(i * 2.3)
        frames.append(frame)
        styled.append(np.clip(art, 0, 255).astype(np.uint8))
        masks.append(occlusion)
    return frames, styled, masks, shift


def warp(array, shift):
    matrix = np.float32([[1, 0, -shift], [0, 1, 0]])
    return cv2.warpAffine(
        array,
        matrix,
        (array.shape[1], array.shape[0]),
        borderMode=cv2.BORDER_REFLECT101,
    )


def gradient(array):
    gray = cv2.cvtColor(array.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    return cv2.magnitude(
        cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    )


def evaluate(kind, quality=False, floor=0.35, clip_path=None):
    sources, fresh, masks, shift = fixture(kind)
    outputs = {"baseline": [fresh[0]], "patched": [fresh[0]]}
    metrics = {
        key: {
            "mc_difference": [],
            "edge_difference": [],
            "ghosting_error": [],
            "detail_retention": [],
        }
        for key in outputs
    }
    timings = []
    for i in range(1, len(sources)):
        prev = cv2.cvtColor(sources[i - 1], cv2.COLOR_RGB2GRAY)
        cur = cv2.cvtColor(sources[i], cv2.COLOR_RGB2GRAY)
        started = time.perf_counter()
        forward, backward = (
            Flow._farneback(prev, cur, quality),
            Flow._farneback(cur, prev, quality),
        )
        timings.append(time.perf_counter() - started)
        cut = Flow._scene_cut(prev, cur, 0.22)[0] or (
            kind == "cut" and i == len(sources) // 2
        )
        confidences = {
            "baseline": legacy_confidence(prev, cur, forward, backward, quality),
            "patched": Flow._transport_confidence(
                prev, cur, forward, backward, quality
            ),
        }
        stable = ~(masks[i] | warp(masks[i - 1].astype(np.uint8), shift).astype(bool))
        stable[:, -max(shift, 1) :] = False
        ghost = masks[i].copy()
        if shift:
            ghost[:, -shift:] = True
        for name, raw in confidences.items():
            confidence = np.clip((raw - floor) / (1 - floor), 0, 1)
            if name == "baseline":
                h, w = cur.shape
                gx, gy = np.meshgrid(
                    np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32)
                )
                transported = cv2.remap(
                    outputs[name][-1],
                    gx + backward[..., 0],
                    gy + backward[..., 1],
                    cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REFLECT101,
                )
            else:
                transported, confidence = Flow._warp_previous(
                    outputs[name][-1],
                    backward,
                    confidence,
                    (cur.shape[1], cur.shape[0]),
                )
            alpha = confidence[..., None] * (0.0 if cut else 0.35)
            output = np.clip(
                fresh[i] * (1 - alpha) + transported * alpha, 0, 255
            ).astype(np.uint8)
            prior = warp(outputs[name][-1], shift)
            if not cut:
                metrics[name]["mc_difference"].append(
                    float(np.abs(output.astype(float) - prior)[stable].mean())
                )
                metrics[name]["edge_difference"].append(
                    float(np.abs(gradient(output) - gradient(prior))[stable].mean())
                )
            if ghost.any():
                metrics[name]["ghosting_error"].append(
                    float(np.abs(output.astype(float) - fresh[i])[ghost].mean())
                )
            metrics[name]["detail_retention"].append(
                float(
                    gradient(output)[stable].mean()
                    / max(1e-6, gradient(fresh[i])[stable].mean())
                )
            )
            outputs[name].append(output)
    report = {
        name: {
            metric: round(float(np.mean(values)), 6) if values else None
            for metric, values in rows.items()
        }
        for name, rows in metrics.items()
    }
    report["flow_pair_ms"] = round(float(np.mean(timings) * 1000), 3)
    if clip_path is not None:
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        frames = np.stack(
            [
                np.concatenate(row, axis=1)
                for row in zip(sources, outputs["baseline"], outputs["patched"])
            ]
        )
        h, w = frames.shape[1:3]
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{w}x{h}",
                "-r",
                "12",
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                str(clip_path),
            ],
            input=frames.tobytes(),
            capture_output=True,
            check=True,
        )
    return report, (sources[-1], outputs["baseline"][-1], outputs["patched"][-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("temporal-report.json"))
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--floor", type=float, default=0.35)
    parser.add_argument(
        "--clips",
        action="store_true",
        help="Also export source | baseline | patched synthetic MP4s (requires ffmpeg)",
    )
    args = parser.parse_args()
    if not 0 <= args.floor <= 0.9:
        parser.error("--floor must be between 0 and 0.9")
    if args.clips and not shutil.which("ffmpeg"):
        parser.error("--clips requires ffmpeg on PATH")
    cv2.setNumThreads(1)
    reports, images = {}, []
    for kind in ("static", "pan", "occlusion", "lighting", "cut"):
        clip = (
            args.output.with_name(f"{args.output.stem}-{kind}.mp4")
            if args.clips
            else None
        )
        reports[kind], row = evaluate(kind, args.quality, args.floor, clip)
        images.append((kind, row))
    result = {
        "baseline_commit": "5341245",
        "transport_version": TRANSPORT_VERSION,
        "fixture_seed": 734,
        "quality": args.quality,
        "confidence_floor": args.floor,
        "numpy": np.__version__,
        "opencv": cv2.__version__,
        "units": "differences: 0-255; detail_retention: gradient ratio; timing: CPU only",
        "limitation": "Generated source and synthetic stylization; no diffusion/artistic acceptance claim.",
        "cases": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    sheet = Image.new("RGB", (3 * 256, len(images) * 190), (18, 19, 24))
    draw = ImageDraw.Draw(sheet)
    for index, (kind, row) in enumerate(images):
        for column, array in enumerate(row):
            sheet.paste(Image.fromarray(array), (column * 256, index * 190 + 28))
            draw.text(
                (column * 256 + 8, index * 190 + 7),
                f"{kind}: {('source', 'baseline', 'patched')[column]}",
                fill="white",
            )
    sheet.save(args.output.with_suffix(".png"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
