"""Zero-dependency Threaded HTTP/JSON Server for the anti-text-watermarks Web Studio."""

from __future__ import annotations

import json
import mimetypes
import pathlib
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse

from ..cli import DEFAULT_DEMO_TEXT
from ..models import PipelineConfig
from ..pipeline import AntiWatermarkPipeline
from ..simulator import TextGrainSimulator

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"


class AntiWatermarkRequestHandler(BaseHTTPRequestHandler):
    """Handles static UI assets and JSON API endpoints."""

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet clean logging
        pass

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, file_path: pathlib.Path) -> None:
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        if file_path.suffix == ".css":
            mime = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            mime = "application/javascript; charset=utf-8"
        elif file_path.suffix == ".html":
            mime = "text/html; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._serve_file(STATIC_DIR / "index.html")
            return

        if path == "/api/demo":
            self._send_json({"demo_text": DEFAULT_DEMO_TEXT})
            return

        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            safe_path = (STATIC_DIR / rel).resolve()
            if str(safe_path).startswith(str(STATIC_DIR)):
                self._serve_file(safe_path)
                return

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw_body)
        except Exception as exc:
            self._send_json({"error": f"Invalid JSON request: {exc}"}, status=400)
            return

        if path == "/api/process":
            self._handle_process(data)
            return

        if path == "/api/simulate":
            self._handle_simulate(data)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "API route not found")

    def _build_config_from_payload(self, data: Dict[str, Any]) -> PipelineConfig:
        preset = data.get("preset", "balanced")
        overrides: Dict[str, Any] = {}
        for field_name in (
            "enable_sanitizer",
            "strip_zero_width",
            "normalize_homoglyphs",
            "normalize_whitespace",
            "normalize_ai_punctuation",
            "protect_markdown",
            "enable_entropy_disruptor",
            "context_window_size",
            "target_edit_rate",
            "enable_syntactic_shift",
            "scrub_ai_cliches",
            "enable_dipper_llm",
            "lex_diversity",
            "order_diversity",
            "llm_provider",
            "llm_base_url",
            "llm_api_key",
            "llm_model",
            "enable_backtranslate",
            "pivot_languages",
        ):
            if field_name in data and data[field_name] is not None:
                overrides[field_name] = data[field_name]
        return PipelineConfig.from_preset(preset, **overrides)

    def _handle_process(self, data: Dict[str, Any]) -> None:
        text = data.get("text", "")
        cfg = self._build_config_from_payload(data)
        pipeline = AntiWatermarkPipeline(cfg)
        result = pipeline.process(text, cfg)
        self._send_json(result.to_dict())

    def _handle_simulate(self, data: Dict[str, Any]) -> None:
        text = data.get("text", "") or DEFAULT_DEMO_TEXT
        secret_key = data.get("secret_key", TextGrainSimulator.DEFAULT_KEY)
        window_size = int(data.get("context_window_size", 4))
        inject_zw = bool(data.get("inject_zero_width", True))

        # 1. Embed genuine textGrain statistical watermark (+ optional zero-width carrier)
        watermarked_text = TextGrainSimulator.embed_watermark(
            text=text,
            secret_key=secret_key,
            window_size=window_size,
            entropy_budget=0.90,
            inject_zero_width=inject_zw,
        )

        # 2. Run detector before attack
        detection_before = TextGrainSimulator.detect_watermark(
            text=watermarked_text,
            secret_key=secret_key,
            window_size=window_size,
        )

        # 3. Attack watermarked text with anti-text-watermarks pipeline
        cfg = self._build_config_from_payload(data)
        pipeline = AntiWatermarkPipeline(cfg)
        result = pipeline.process(watermarked_text, cfg)

        # 4. Run detector after attack
        detection_after = TextGrainSimulator.detect_watermark(
            text=result.output_text,
            secret_key=secret_key,
            window_size=window_size,
        )

        self._send_json(
            {
                "watermarked_text": watermarked_text,
                "attacked_text": result.output_text,
                "detection_before": detection_before.to_dict(),
                "detection_after": detection_after.to_dict(),
                "pipeline_result": result.to_dict(),
            }
        )


def create_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), AntiWatermarkRequestHandler)


def run_web_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = create_server(host=host, port=port)
    url = f"http://{host}:{port}"
    print(f"🚀 anti-text-watermarks Web Studio running at {url}")
    print("Press Ctrl+C to stop the server.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Web Studio server...")
        server.server_close()
