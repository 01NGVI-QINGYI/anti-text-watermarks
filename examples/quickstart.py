"""Quickstart example for anti-text-watermarks Python SDK."""

from anti_text_watermarks import (
    AntiWatermarkPipeline,
    PipelineConfig,
    TextGrainSimulator,
    remove_watermarks,
)


def main() -> None:
    sample_text = (
        "值得注意的是，在当今数字化时代，大规模语言模型生成的内容扮演着至关重要的角色。\n"
        "然而，由于模型在生成文本时会通过最优传输算法引入微弱的统计偏移，因此检测器可以利用密钥识别这些潜在的特征。\n"
        "Furthermore, statistical watermarks like textGrain delve into high-entropy vocabulary blocks "
        "while leaving inline formulas like $D_{KL}(P \\parallel Q)$ and URLs like https://openai.com intact."
    )

    # 1. Embed a real simulated textGrain + Zero-Width watermark
    secret_key = "demo-secret-key-2026"
    watermarked = TextGrainSimulator.embed_watermark(
        sample_text,
        secret_key=secret_key,
        window_size=4,
        entropy_budget=0.90,
        inject_zero_width=True,
    )

    det_before = TextGrainSimulator.detect_watermark(watermarked, secret_key=secret_key)
    print(f"[Before Attack] Combined Z-Score: {det_before.combined_z_score:.3f} | Verdict: {det_before.verdict}")

    # 2. One-line watermark removal (Balanced preset)
    result = remove_watermarks(watermarked, preset="balanced")

    det_after = TextGrainSimulator.detect_watermark(result.output_text, secret_key=secret_key)
    print(f"[After Attack]  Combined Z-Score: {det_after.combined_z_score:.3f} | Verdict: {det_after.verdict}")
    print(f"[Forensics]     4-gram Windows Broken: {result.forensics.ngram_4_broken_ratio * 100:.1f}%")
    print(f"[Forensics]     Est. textGrain Survival: {result.forensics.estimated_textgrain_before * 100:.1f}% -> {result.forensics.estimated_textgrain_after * 100:.1f}%")
    print("\n--- Cleaned Output ---\n" + result.output_text)


if __name__ == "__main__":
    main()
