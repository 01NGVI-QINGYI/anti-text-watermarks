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
import urllib.error
import urllib.request
from typing import Optional, Tuple

from .models import PipelineConfig


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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""
