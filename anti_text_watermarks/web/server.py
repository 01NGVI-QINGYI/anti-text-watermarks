"""Zero-dependency Threaded HTTP/JSON Server for the anti-text-watermarks Web Studio."""

from __future__ import annotations

import json
import ipaddress
import math
import mimetypes
import pathlib
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, Optional, Set, Tuple
from urllib.parse import urlparse, urlsplit

from ..cli import DEFAULT_DEMO_TEXT
from ..models import PipelineConfig
from ..pipeline import AntiWatermarkPipeline
from ..simulator import TextGrainSimulator

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"
MAX_REQUEST_BODY_BYTES = 256 * 1024
MAX_TEXT_CHARS = 20_000
MAX_CONTEXT_WINDOW_SIZE = 6
MAX_TARGET_EDIT_RATE = 0.60
MAX_PIVOT_LANGUAGES = 2
MAX_CONCURRENT_REQUESTS = 8
REQUEST_SOCKET_TIMEOUT_SECONDS = 10
REQUEST_BODY_TIMEOUT_SECONDS = 10
MAX_LLM_URL_CHARS = 2048
MAX_LLM_API_KEY_CHARS = 4096
MAX_LLM_MODEL_CHARS = 256
MAX_SIMULATOR_KEY_CHARS = 4096
DEFAULT_ALLOWED_LLM_ORIGINS = (
    "http://localhost:11434",
    "http://127.0.0.1:11434",
    "https://api.openai.com",
)


def _normalize_origin(value: str) -> Tuple[str, str, int]:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("origin is invalid") from exc
    scheme = parsed.scheme.lower()
    if (
        scheme not in ("http", "https")
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("origin must be an HTTP(S) origin without credentials or query data")
    try:
        normalized_host = str(ipaddress.ip_address(hostname))
    except ValueError:
        normalized_host = hostname.rstrip(".").lower()
    normalized_port = port if port is not None else (443 if scheme == "https" else 80)
    if not 1 <= normalized_port <= 65535:
        raise ValueError("origin port is invalid")
    return scheme, normalized_host, normalized_port


def _request_origin_key(host_header: str, scheme: str) -> Optional[Tuple[str, str, int]]:
    try:
        parsed = urlsplit(f"//{host_header}")
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not hostname or parsed.username is not None or parsed.password is not None or parsed.path:
        return None
    try:
        normalized_host = str(ipaddress.ip_address(hostname))
    except ValueError:
        normalized_host = hostname.rstrip(".").lower()
    normalized_port = port if port is not None else (443 if scheme == "https" else 80)
    if not 1 <= normalized_port <= 65535:
        return None
    return scheme, normalized_host, normalized_port


def _normalize_llm_origins(origins: Optional[Iterable[str]]) -> Set[Tuple[str, str, int]]:
    values = list(DEFAULT_ALLOWED_LLM_ORIGINS)
    if origins:
        values.extend(origins)
    allowed = set()
    for origin in values:
        normalized = _normalize_origin(origin)
        if normalized[0] == "http":
            host = normalized[1]
            try:
                is_loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                is_loopback = host == "localhost"
            if not is_loopback:
                raise ValueError("HTTP LLM origins must use a loopback host")
        allowed.add(normalized)
    return allowed


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded server with a hard cap on simultaneous request handlers."""

    request_queue_size = MAX_CONCURRENT_REQUESTS

    def __init__(self, server_address: Any, request_handler_class: Any) -> None:
        self._request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        super().__init__(server_address, request_handler_class)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._request_slots.acquire(blocking=False):
            response = (
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Connection: close\r\n"
                b"Content-Length: 0\r\n\r\n"
            )
            try:
                request.sendall(response)
            except OSError:
                pass
            self.shutdown_request(request)
            return

        try:
            worker = threading.Thread(
                target=self.process_request_thread,
                args=(request, client_address),
                daemon=self.daemon_threads,
            )
            worker.start()
        except Exception:
            self._request_slots.release()
            self.handle_error(request, client_address)
            self.shutdown_request(request)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class AntiWatermarkRequestHandler(BaseHTTPRequestHandler):
    """Handles static UI assets and JSON API endpoints."""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_SOCKET_TIMEOUT_SECONDS)

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet clean logging
        pass

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_same_origin_request(self) -> bool:
        origin = self.headers.get("Origin")
        fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if fetch_site and fetch_site not in ("same-origin", "none"):
            return False
        request_host = self.headers.get("Host", "")
        allowed_origins = self.server.allowed_web_origins
        if not origin:
            return any(
                _request_origin_key(request_host, scheme) == allowed
                for allowed in allowed_origins
                for scheme in (allowed[0],)
            )
        if origin == "null":
            return False
        try:
            parsed_origin = urlsplit(origin)
            origin_key = _normalize_origin(origin)
        except ValueError:
            return False
        if parsed_origin.path not in ("", "/"):
            return False
        return (
            origin_key in allowed_origins
            and _request_origin_key(request_host, origin_key[0]) == origin_key
        )

    @staticmethod
    def _validated_text(value: Any, default: str, empty_uses_default: bool = False) -> str:
        if value is None:
            value = default
        if not isinstance(value, str):
            raise ValueError("text must be a string")
        if empty_uses_default and not value:
            value = default
        if len(value) > MAX_TEXT_CHARS:
            raise ValueError(f"text exceeds the {MAX_TEXT_CHARS}-character limit")
        return value

    def _validate_llm_url(self, value: str) -> None:
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("llm_base_url is invalid") from exc
        if (
            parsed.scheme.lower() not in ("http", "https")
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("llm_base_url must be an HTTP(S) URL without embedded credentials")

        normalized_host = hostname.rstrip(".").lower()
        is_loopback = normalized_host == "localhost"
        try:
            normalized_host = str(ipaddress.ip_address(hostname))
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass
        scheme = parsed.scheme.lower()
        if scheme == "http" and not is_loopback:
            raise ValueError("Non-loopback LLM endpoints must use HTTPS")
        normalized_port = port if port is not None else (443 if scheme == "https" else 80)
        if not 1 <= normalized_port <= 65535:
            raise ValueError("llm_base_url port is invalid")
        if (scheme, normalized_host, normalized_port) not in self.server.allowed_llm_origins:
            raise ValueError("llm_base_url origin is not in the Web Studio allowlist")

    def _read_json_body(self) -> Dict[str, Any]:
        transfer_encoding = self.headers.get("Transfer-Encoding")
        content_lengths = self.headers.get_all("Content-Length") or []
        if transfer_encoding or len(content_lengths) > 1:
            self.close_connection = True
            raise ValueError("unsupported or ambiguous request body framing")

        try:
            length = int(content_lengths[0]) if content_lengths else 0
        except ValueError as exc:
            self.close_connection = True
            raise ValueError("Content-Length must be a non-negative integer") from exc
        if length < 0:
            self.close_connection = True
            raise ValueError("Content-Length must be a non-negative integer")
        if length > MAX_REQUEST_BODY_BYTES:
            self.close_connection = True
            raise OverflowError(f"request body exceeds the {MAX_REQUEST_BODY_BYTES}-byte limit")

        raw_body = b"{}"
        if length:
            deadline = time.monotonic() + REQUEST_BODY_TIMEOUT_SECONDS
            chunks = []
            remaining = length
            read_chunk = getattr(self.rfile, "read1", self.rfile.read)
            try:
                while remaining:
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        raise TimeoutError("request body read timed out")
                    self.connection.settimeout(timeout)
                    chunk = read_chunk(min(remaining, 64 * 1024))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
            except OSError as exc:
                self.close_connection = True
                raise ValueError("request body could not be read within the time limit") from exc
            finally:
                self.connection.settimeout(REQUEST_SOCKET_TIMEOUT_SECONDS)
            raw_body = b"".join(chunks)
        if len(raw_body) != length and length:
            self.close_connection = True
            raise ValueError("request body ended before Content-Length bytes were received")
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("request JSON must be an object")
        return data

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
        if not self._is_same_origin_request():
            self.close_connection = True
            self.send_error(HTTPStatus.FORBIDDEN, "Cross-origin requests are not allowed")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
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
        if not self._is_same_origin_request():
            self.close_connection = True
            self.send_error(HTTPStatus.FORBIDDEN, "Cross-origin requests are not allowed")
            return

        parsed = urlparse(self.path)
        path = parsed.path

        try:
            data = self._read_json_body()
        except OverflowError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus(413))
            return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            if path == "/api/process":
                self._handle_process(data)
                return

            if path == "/api/simulate":
                self._handle_simulate(data)
                return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "API route not found")

    def _build_config_from_payload(self, data: Dict[str, Any]) -> PipelineConfig:
        preset = data.get("preset", "balanced")
        allowed_presets = {"stealth", "balanced", "aggressive", "dipper", "backtranslate", "custom"}
        if not isinstance(preset, str) or preset.strip().lower() not in allowed_presets:
            raise ValueError("preset is not supported")
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

        boolean_fields = (
            "enable_sanitizer",
            "strip_zero_width",
            "normalize_homoglyphs",
            "normalize_whitespace",
            "normalize_ai_punctuation",
            "protect_markdown",
            "enable_entropy_disruptor",
            "enable_syntactic_shift",
            "scrub_ai_cliches",
            "enable_dipper_llm",
            "enable_backtranslate",
        )
        for field_name in boolean_fields:
            if field_name in overrides and not isinstance(overrides[field_name], bool):
                raise ValueError(f"{field_name} must be a boolean")

        for field_name in ("context_window_size", "lex_diversity", "order_diversity"):
            if field_name in overrides and type(overrides[field_name]) is not int:
                raise ValueError(f"{field_name} must be an integer")

        config = PipelineConfig.from_preset(preset, **overrides)
        if not 2 <= config.context_window_size <= MAX_CONTEXT_WINDOW_SIZE:
            raise ValueError(f"context_window_size must be between 2 and {MAX_CONTEXT_WINDOW_SIZE}")
        if "target_edit_rate" in overrides:
            rate = overrides["target_edit_rate"]
            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                raise ValueError("target_edit_rate must be a finite number")
            if isinstance(rate, float) and not math.isfinite(rate):
                raise ValueError("target_edit_rate must be a finite number")
            if rate < 0.0 or rate > MAX_TARGET_EDIT_RATE:
                raise ValueError(f"target_edit_rate must be between 0 and {MAX_TARGET_EDIT_RATE}")
        for field_name in ("lex_diversity", "order_diversity"):
            value = getattr(config, field_name)
            if not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100")

        if "llm_provider" in overrides:
            provider = overrides["llm_provider"]
            if not isinstance(provider, str) or provider.lower() not in ("ollama", "openai"):
                raise ValueError("llm_provider must be ollama or openai")
            config.llm_provider = provider.lower()

        for field_name, max_length in (
            ("llm_base_url", MAX_LLM_URL_CHARS),
            ("llm_api_key", MAX_LLM_API_KEY_CHARS),
            ("llm_model", MAX_LLM_MODEL_CHARS),
        ):
            value = getattr(config, field_name)
            if not isinstance(value, str) or len(value) > max_length:
                raise ValueError(f"{field_name} must be a string of at most {max_length} characters")
        if config.enable_dipper_llm or config.enable_backtranslate:
            if not config.llm_base_url:
                raise ValueError("llm_base_url is required when an LLM stage is enabled")
            self._validate_llm_url(config.llm_base_url)

        if not isinstance(config.pivot_languages, list) or len(config.pivot_languages) > MAX_PIVOT_LANGUAGES:
            raise ValueError(f"pivot_languages must contain at most {MAX_PIVOT_LANGUAGES} languages")
        if any(
            not isinstance(language, str) or not language.strip() or len(language) > 32
            for language in config.pivot_languages
        ):
            raise ValueError("each pivot language must be a non-empty string of at most 32 characters")
        return config

    def _handle_process(self, data: Dict[str, Any]) -> None:
        text = self._validated_text(data.get("text", ""), default="")
        cfg = self._build_config_from_payload(data)
        pipeline = AntiWatermarkPipeline(cfg)
        result = pipeline.process(text, cfg)
        self._send_json(result.to_dict())

    def _handle_simulate(self, data: Dict[str, Any]) -> None:
        text = self._validated_text(data.get("text"), default=DEFAULT_DEMO_TEXT, empty_uses_default=True)
        cfg = self._build_config_from_payload(data)
        secret_key = data.get("secret_key", TextGrainSimulator.DEFAULT_KEY)
        if not isinstance(secret_key, str) or len(secret_key) > MAX_SIMULATOR_KEY_CHARS:
            raise ValueError(f"secret_key must be a string of at most {MAX_SIMULATOR_KEY_CHARS} characters")
        window_size = cfg.context_window_size
        inject_zw = data.get("inject_zero_width", True)
        if not isinstance(inject_zw, bool):
            raise ValueError("inject_zero_width must be a boolean")

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


def _loopback_bind_host(host: str) -> str:
    if not isinstance(host, str):
        raise ValueError("Web Studio host must be a loopback IP address")
    normalized = host.strip().lower()
    if normalized == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError(
            "Web Studio only binds to a loopback IP. For remote use, bind to 127.0.0.1 "
            "and use an authenticated HTTPS reverse proxy."
        ) from exc
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_loopback:
        raise ValueError(
            "Web Studio only binds to a loopback IP. For remote use, bind to 127.0.0.1 "
            "and use an authenticated HTTPS reverse proxy."
        )
    return str(address)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    trusted_origin: Optional[str] = None,
    allowed_llm_origins: Optional[Iterable[str]] = None,
) -> ThreadingHTTPServer:
    safe_host = _loopback_bind_host(host)
    server = BoundedThreadingHTTPServer((safe_host, port), AntiWatermarkRequestHandler)
    local_port = int(server.server_address[1])
    allowed_web_origins = {("http", safe_host, local_port)}
    if safe_host == "127.0.0.1":
        allowed_web_origins.add(("http", "localhost", local_port))
    if trusted_origin:
        try:
            parsed_trusted_origin = urlsplit(trusted_origin)
            trusted_origin_key = _normalize_origin(trusted_origin)
        except ValueError as exc:
            server.server_close()
            raise ValueError("trusted_origin must be a valid HTTPS origin") from exc
        if parsed_trusted_origin.path not in ("", "/") or trusted_origin_key[0] != "https":
            server.server_close()
            raise ValueError("trusted_origin must be a valid HTTPS origin without a path")
        allowed_web_origins.add(trusted_origin_key)
    try:
        server.allowed_llm_origins = frozenset(_normalize_llm_origins(allowed_llm_origins))
    except ValueError:
        server.server_close()
        raise
    server.allowed_web_origins = frozenset(allowed_web_origins)
    return server


def run_web_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    trusted_origin: Optional[str] = None,
    allowed_llm_origins: Optional[Iterable[str]] = None,
) -> None:
    server = create_server(
        host=host,
        port=port,
        trusted_origin=trusted_origin,
        allowed_llm_origins=allowed_llm_origins,
    )
    url = f"http://{server.server_address[0]}:{server.server_address[1]}"
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
