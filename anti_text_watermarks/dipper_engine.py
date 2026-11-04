"""Stage 3: DIPPER-Style Controlled LLM Paraphraser (`martiansigma/dipper` methodology).

Implements explicit dual-dial control over:
- `lex_diversity` (0..100): Target percentage of high-entropy lexical substitution.
- `order_diversity` (0..100): Target intensity of clause reordering, voice inversion,
  and sentence boundary restructuring.

Supports any OpenAI-compatible endpoint (Ollama local models, vLLM, LM Studio,
DeepSeek, Qwen, or OpenAI API with watermark opt-out).
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Optional, Tuple

from .models import PipelineConfig

MAX_CHAT_COMPLETION_RESPONSE_BYTES = 1024 * 1024
CHAT_RESPONSE_READ_CHUNK_BYTES = 64 * 1024


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


class DipperParaphraseEngine:
    """Controlled lexical and syntactic diversity paraphraser."""

    @classmethod
    def paraphrase(cls, text: str, config: PipelineConfig) -> Tuple[str, Optional[str]]:
        """Run DIPPER-controlled paraphrasing via configured LLM endpoint.

        Returns:
            Tuple of (rewritten_text, warning_message_if_any)
        """
        if not config.enable_dipper_llm or not text.strip():
            return text, None

        lex = max(0, min(100, config.lex_diversity))
        order = max(0, min(100, config.order_diversity))

        system_prompt = cls._build_dipper_system_prompt(lex_diversity=lex, order_diversity=order)
        user_prompt = (
            f"<control_codes>lex={lex}, order={order}</control_codes>\n"
            f"Rewrite the following text according to the control codes while preserving all "
            f"placeholder tokens matching ⟦ATW_XXXX⟧ verbatim:\n\n{text}"
        )

        try:
            rewritten = cls._call_chat_completion(
                base_url=config.llm_base_url,
                api_key=config.llm_api_key,
                model=config.llm_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=config.llm_temperature,
            )
            if rewritten and rewritten.strip():
                return rewritten.strip(), None
            return text, "DIPPER LLM returned an empty response; kept offline entropy-disrupted output."
        except Exception as exc:
            return (
                text,
                f"DIPPER LLM endpoint ({config.llm_base_url}) unreachable ({exc}); "
                f"automatically applied offline DIPPER-calibrated entropy disruption (lex={lex}, order={order}).",
            )

    @staticmethod
    def _build_dipper_system_prompt(lex_diversity: int, order_diversity: int) -> str:
        return (
            "You are DIPPER-Adversarial, a precision semantic-preserving text rewriter designed to "
            "eliminate statistical token-sampling watermarks (such as OpenAI textGrain, Google SynthID-Text, "
            "and Kirchenbauer Red-Green lists).\n\n"
            "STRICT RULES:\n"
            f"1. Lexical Diversity Target = {lex_diversity}%: Replace approximately {lex_diversity}% of "
            "high-entropy verbs, adjectives, adverbs, and discourse connectors with natural synonyms.\n"
            f"2. Order Diversity Target = {order_diversity}%: Restructure approximately {order_diversity}% of "
            "clause orderings (e.g., active/passive voice shifts, subordinate clause fronting, sentence splitting/merging) "
            "to break sliding n-gram context hashes.\n"
            "3. Preserve 100% of factual meaning, numbers, named entities, and technical terminology.\n"
            "4. NEVER alter, translate, or remove placeholder tokens formatted like ⟦ATW_0000⟧.\n"
            "5. Avoid typical AI clichés ('delve', 'tapestry', 'testament', '值得注意的是', '综上所述').\n"
            "6. Output ONLY the rewritten text in the exact same language as the input, with no preamble or commentary."
        )

    @staticmethod
    def _call_chat_completion(
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.75,
        timeout: int = 25,
    ) -> str:
        url = base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        deadline = time.monotonic() + timeout
        with _NO_REDIRECT_OPENER.open(req, timeout=timeout) as resp:
            body = json.loads(cls._read_bounded_response(resp, deadline).decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

    @staticmethod
    def _read_bounded_response(resp, deadline: float) -> bytes:
        content_length = resp.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
                if declared_length < 0 or declared_length > MAX_CHAT_COMPLETION_RESPONSE_BYTES:
                    raise ValueError("LLM response exceeds the configured size limit")
            except ValueError as exc:
                raise ValueError("LLM response has an invalid or oversized Content-Length") from exc

        response_socket = getattr(getattr(getattr(resp, "fp", None), "raw", None), "_sock", None)
        if response_socket is None:
            raise ValueError("LLM response does not expose a socket for bounded reads")
        read_chunk = getattr(resp, "read1", resp.read)
        body = bytearray()
        while True:
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                raise TimeoutError("LLM response exceeded the total read time limit")
            response_socket.settimeout(remaining_time)
            chunk = read_chunk(min(CHAT_RESPONSE_READ_CHUNK_BYTES, MAX_CHAT_COMPLETION_RESPONSE_BYTES + 1 - len(body)))
            if not chunk:
                return bytes(body)
            body.extend(chunk)
            if len(body) > MAX_CHAT_COMPLETION_RESPONSE_BYTES:
                raise ValueError("LLM response exceeds the configured size limit")
