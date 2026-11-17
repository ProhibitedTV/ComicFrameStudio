"""Optional native Tk integration smoke with generated media and mocked WebUI.

Requires a display, ffmpeg/ffprobe and project dependencies. No backend is used.
Run: python tools/smoke_desktop.py --output docs/evidence/native-smoke.json
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
import app
import comicframe_product as product
from comicframe_ui import ComicFrameStudioUI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("native-smoke.json"))
    parser.add_argument(
        "--controlnet",
        action="store_true",
        help="Exercise a mocked source-Canny structural rail",
    )
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix="comicframe-native-smoke-")
    root = Path(temporary.name)
    source = root / "authorized generated source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=384x216:r=4:d=1.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.5",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    payloads, errors = [], []

    class Response:
        ok = True
        status_code = 200
        text = ""

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

        def raise_for_status(self):
            pass

    def api(method, url, **kwargs):
        endpoint = url.split("7860")[-1].split("?")[0]
        if endpoint.endswith("/img2img"):
            payload = kwargs["json"]
            payloads.append(payload)
            image = Image.open(
                BytesIO(base64.b64decode(payload["init_images"][0]))
            ).convert("RGB")
            image = image.resize((payload["width"], payload["height"]))
            stream = BytesIO()
            image.save(stream, format="PNG")
            return Response({"images": [base64.b64encode(stream.getvalue()).decode()]})
        data = {
            "/sdapi/v1/options": {"sd_model_checkpoint": "mock_sd15"},
            "/openapi.json": {
                "paths": {"/sdapi/v1/options": {}, "/sdapi/v1/img2img": {}}
            },
            "/sdapi/v1/sd-models": [{"title": "mock_sd15", "model_name": "mock_sd15"}],
            "/sdapi/v1/samplers": [{"name": "DPM++ 2M"}],
            "/sdapi/v1/schedulers": [{"name": "Automatic"}],
            "/sdapi/v1/memory": {"cuda": {"system": {"total": 12 * 1024**3}}},
            "/sdapi/v1/loras": [],
            "/controlnet/model_list": {"model_list": ["control_v11p_sd15_canny"]},
            "/controlnet/module_list": {"module_list": ["canny"]},
            "/controlnet/settings": {"control_net_unit_count": 1},
            "/sdapi/v1/progress": {"progress": 0, "state": {"job_count": 0}},
        }
        return Response(data.get(endpoint, {}))

    report = {
        "backend": "mocked Forge/A1111 responses; not a visual diffusion assessment",
        "errors": errors,
    }
    with (
        patch.object(ComicFrameStudioUI, "_sync_webui_background", lambda self: None),
        patch.object(product, "preferences_path", lambda: root / "prefs.json"),
        patch("requests.request", api),
        patch("requests.get", lambda url, **kwargs: api("GET", url, **kwargs)),
        patch("requests.post", lambda url, **kwargs: api("POST", url, **kwargs)),
        patch("tkinter.messagebox.showerror", lambda *args: errors.append(args)),
    ):
        window = app.ComicFrameStudioApp()
        window.deiconify()
        window.update()
        window.update_idletasks()
        report["geometry"] = {
            "height": window.winfo_height(),
            "width": window.winfo_width(),
            "mapped": window.winfo_ismapped(),
            "state": window.state(),
        }
        report["controls"] = {}
        report["shell_layout"] = [
            dict(
                name=str(child),
                y=child.winfo_y(),
                height=child.winfo_height(),
                requested_height=child.winfo_reqheight(),
                mapped=child.winfo_ismapped(),
            )
            for child in window.simple_shell.winfo_children()
        ]
        for name in (
            "simple_preview_button",
            "simple_process_button",
            "simple_cancel_button",
            "simple_open_button",
        ):
            widget = getattr(window, name)
            top = widget.winfo_rooty() - window.winfo_rooty()
            report["controls"][name] = {
                "top": top,
                "bottom": top + widget.winfo_height(),
                "height": widget.winfo_height(),
            }
        window.video_var.set(str(source))
        window.work_var.set(str(root / "source_comicframe"))
        window.simple_process_var.set("Dream Rotoscope")
        window.simple_controlnet_var.set(args.controlnet)
        window.simple_steps_var.set(12)
        window._simple_preview_clicked()
        started = time.monotonic()
        stage = ["preview"]

        def poll():
            if time.monotonic() - started > 45:
                errors.append(("timeout", stage[0]))
                window.destroy()
                return
            if window._simple_busy:
                window.after(50, poll)
                return
            if stage[0] == "preview":
                report["preview_status"] = window.progress_label_var.get()
                if "Preview ready" not in report["preview_status"]:
                    errors.append(("preview-status", report["preview_status"]))
                report["preview_requests"] = len(payloads)
                report["preview_restored_project"] = window.work_var.get() == str(
                    root / "source_comicframe"
                )
                report["controls_live"] = {}
                for name in report["controls"]:
                    widget = getattr(window, name)
                    top = widget.winfo_rooty() - window.winfo_rooty()
                    report["controls_live"][name] = dict(
                        top=top,
                        bottom=top + widget.winfo_height(),
                        height=widget.winfo_height(),
                        mapped=widget.winfo_ismapped(),
                    )
                stage[0] = "full"
                window._simple_process_clicked()
                window.after(50, poll)
                return
            report["full_status"] = window.progress_label_var.get()
            report["full_result_exists"] = (
                window._simple_output_path is not None
                and window._simple_output_path.is_file()
            )
            report["total_requests"] = len(payloads)
            report["all_steps_12"] = all(p["steps"] == 12 for p in payloads)
            report["no_controlnet_units"] = all(
                not p.get("alwayson_scripts", {}).get("controlnet", {}).get("args", [])
                for p in payloads
            )
            if args.controlnet:
                geometry = []
                for index, payload in enumerate(payloads):
                    frame_dir = (
                        root / "source_comicframe" / "frames"
                        if index
                        else root
                        / "source_comicframe"
                        / "previews"
                        / "first_frame"
                        / "frames"
                    )
                    source_frame = frame_dir / f"frame_{max(1, index):06d}.png"
                    units = (
                        payload.get("alwayson_scripts", {})
                        .get("controlnet", {})
                        .get("args", [])
                    )
                    geometry.append(
                        bool(units)
                        and base64.b64decode(units[0]["image"])
                        == source_frame.read_bytes()
                    )
                report["controlnet_uses_untouched_source"] = all(geometry)
                if not all(geometry):
                    errors.append(("controlnet-geometry", geometry))
            elif not report["no_controlnet_units"]:
                errors.append(("controlnet-off", "unexpected unit"))
            if not report["full_result_exists"] or report["total_requests"] != 7:
                errors.append(("full-render", report["total_requests"]))
            for control in report["controls_live"].values():
                if not control["mapped"] or control["bottom"] > window.winfo_height():
                    errors.append(("layout", control))
            window.destroy()

        window.after(50, poll)
        window.mainloop()
    target = args.output
    target.parent.mkdir(exist_ok=True, parents=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    temporary.cleanup()
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
