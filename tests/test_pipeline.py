"""Automated unit & integration tests for anti-text-watermarks."""

from __future__ import annotations

import json
import threading
import urllib.request

from anti_text_watermarks import (
    AntiWatermarkPipeline,
    MarkdownGuard,
    PipelineConfig,
    TextGrainSimulator,
    UnicodeSanitizer,
    remove_watermarks,
)
from anti_text_watermarks.cli import DEFAULT_DEMO_TEXT
from anti_text_watermarks.web.server import create_server


def test_stage1_unicode_sanitizer_strips_zero_width_and_homoglyphs() -> None:
    # Mix zero-width space (\u200b), tag char (\U000e0041), Cyrillic 'а' (\u0430) in 'watermаrk', and atypical space (\u00a0)
    dirty = "This\u00a0is\u200b a w\u0430term\u0430rk\U000e0041 — really subtle."
    cfg = PipelineConfig.from_preset("balanced")
    cleaned, stats = UnicodeSanitizer.sanitize(dirty, cfg)

    assert "\u200b" not in cleaned
    assert "\U000e0041" not in cleaned
    assert "\u0430" not in cleaned
    assert "watermark" in cleaned
    assert stats.zero_width_removed == 1
    assert stats.tag_chars_removed == 1
    assert stats.homoglyphs_normalized == 2
    assert stats.atypical_spaces_normalized == 1


def test_markdown_guard_preserves_code_math_and_urls() -> None:
    sample = (
        "值得注意的是，这段代码 ```python\ndef delve_into(x):\n    return x + 1\n``` "
        "以及行内公式 $E = mc^2$ 和链接 https://openai.com/textgrain 必须原封不动。"
    )
    res = remove_watermarks(sample, preset="aggressive")
    assert "```python\ndef delve_into(x):\n    return x + 1\n```" in res.output_text
    assert "$E = mc^2$" in res.output_text
    assert "https://openai.com/textgrain" in res.output_text
    assert "值得注意的是" not in res.output_text


def test_stage2_entropy_disruptor_breaks_ngram_hashes() -> None:
    res = remove_watermarks(DEFAULT_DEMO_TEXT, preset="balanced")
    assert res.output_text != DEFAULT_DEMO_TEXT
    assert res.forensics.token_edit_rate > 0.08
    assert res.forensics.ngram_4_broken_ratio > 0.35
    assert res.forensics.estimated_textgrain_after < res.forensics.estimated_textgrain_before


def test_textgrain_simulator_embed_and_attack_collapses_z_score() -> None:
    key = "test-secret-key-2026"
    watermarked = TextGrainSimulator.embed_watermark(
        DEFAULT_DEMO_TEXT,
        secret_key=key,
        window_size=4,
        entropy_budget=0.92,
        inject_zero_width=True,
    )
    det_before = TextGrainSimulator.detect_watermark(watermarked, secret_key=key, window_size=4)
    assert det_before.combined_z_score > 2.0
    assert det_before.is_watermarked is True

    # Attack with balanced pipeline
    attacked = remove_watermarks(watermarked, preset="balanced")
    det_after = TextGrainSimulator.detect_watermark(attacked.output_text, secret_key=key, window_size=4)

    # Z-score must drop sharply and fall below watermark detection threshold
    assert det_after.combined_z_score < det_before.combined_z_score - 1.5
    assert det_after.combined_z_score < 2.0
    assert det_after.is_watermarked is False
    assert attacked.forensics.hidden_unicode_count_after == 0


def test_web_studio_api_endpoints() -> None:
    server = create_server(host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # 1. Test GET /
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
            assert "anti-text-watermarks" in html

        # 2. Test POST /api/process
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/process",
            data=json.dumps({"text": DEFAULT_DEMO_TEXT, "preset": "balanced"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            assert "output_text" in payload
            assert payload["forensics"]["estimated_textgrain_after"] < 0.35

        # 3. Test POST /api/simulate
        sim_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/simulate",
            data=json.dumps({"text": DEFAULT_DEMO_TEXT, "preset": "balanced"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(sim_req, timeout=5) as resp:
            sim_data = json.loads(resp.read().decode("utf-8"))
            assert sim_data["detection_before"]["combined_z_score"] > sim_data["detection_after"]["combined_z_score"]
    finally:
        server.shutdown()
        server.server_close()
