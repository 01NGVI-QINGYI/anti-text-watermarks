"""Command-Line Interface for anti-text-watermarks (`atw` / `anti-text-watermarks`)."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Optional

from .models import PipelineConfig, PipelineResult
from .pipeline import AntiWatermarkPipeline
from .simulator import TextGrainSimulator


DEFAULT_DEMO_TEXT = (
    "值得注意的是，在当今数字化时代，大规模语言模型生成的内容扮演着至关重要的角色。\n"
    "然而，由于模型在生成文本时会通过最优传输算法引入微弱的统计偏移，因此检测器可以利用密钥识别这些潜在的特征。\n"
    "如果我们需要保护隐私并消除这种统计关联，那么就必须采用有效的词汇替换与句式重构方法，从而彻底打乱局部上下文窗口的哈希序列。\n"
    "Furthermore, it is important to note that statistical watermarks like textGrain delve into "
    "high-entropy vocabulary blocks. Consequently, modifying approximately 25% of pivotal tokens "
    "significantly reduces detection accuracy while preserving the core meaning of the document, "
    "including protected spans like `z_score < 1.64` and https://openai.com."
)


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _print_report(result: PipelineResult) -> None:
    f = result.forensics
    s = result.sanitizer_stats
    d = result.disruption_stats

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        console.print(
            Panel.fit(
                "[bold cyan]anti-text-watermarks[/bold cyan] — Multi-Layer Adversarial Report",
                border_style="cyan",
            )
        )

        table = Table(title="Watermark Disruption & Forensics Metrics", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="bold")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Delta / Status", justify="right")

        table.add_row(
            "Est. textGrain Detection Rate",
            f"[red]{f.estimated_textgrain_before * 100:.1f}%[/red]",
            f"[green]{f.estimated_textgrain_after * 100:.1f}%[/green]",
            f"[bold green]-{(f.estimated_textgrain_before - f.estimated_textgrain_after) * 100:.1f}%[/bold green]",
        )
        table.add_row(
            "Trajectory Pivotal Z-Score",
            f"[red]{f.simulated_z_score_before:.2f}[/red] (p={f.simulated_p_value_before:.4f})",
            f"[green]{f.simulated_z_score_after:.2f}[/green] (p={f.simulated_p_value_after:.4f})",
            "[bold green]BELOW THRESHOLD[/bold green]" if f.simulated_z_score_after < 1.65 else "[yellow]WEAK SIGNAL[/yellow]",
        )
        table.add_row(
            "Token Edit Rate",
            "0.0%",
            f"{f.token_edit_rate * 100:.1f}%",
            f"{d.tokens_perturbed} pivots + {d.clauses_reordered} clauses",
        )
        table.add_row(
            "3-gram / 4-gram / 5-gram Broken",
            "0% / 0% / 0%",
            f"{f.ngram_3_broken_ratio * 100:.1f}% / {f.ngram_4_broken_ratio * 100:.1f}% / {f.ngram_5_broken_ratio * 100:.1f}%",
            "[bold cyan]Cascade Hash Invalidated[/bold cyan]",
        )
        table.add_row(
            "Hidden Unicode / Homoglyphs",
            str(f.hidden_unicode_count_before),
            str(f.hidden_unicode_count_after),
            f"Stripped {s.zero_width_removed + s.tag_chars_removed + s.homoglyphs_normalized}",
        )
        table.add_row(
            "AI Cliché Density (per 100w)",
            f"{f.ai_cliche_density_before:.2f}",
            f"{f.ai_cliche_density_after:.2f}",
            f"Scrubbed {d.cliches_replaced} clichés",
        )
        table.add_row(
            "Semantic Preservation",
            "100.0%",
            f"{f.semantic_similarity * 100:.1f}%",
            f"Protected {s.protected_spans_count} code/URL spans",
        )
        console.print(table)

        if result.warnings:
            for w in result.warnings:
                console.print(f"[yellow]Notice:[/yellow] {w}")

        console.print(Panel(result.output_text, title="[bold green]Cleaned & De-Watermarked Output[/bold green]", border_style="green"))
    except ImportError:
        print("=" * 72)
        print("anti-text-watermarks — Adversarial Forensics Report")
        print("=" * 72)
        print(
            f"Est. textGrain Detection: {f.estimated_textgrain_before * 100:.1f}% -> {f.estimated_textgrain_after * 100:.1f}%"
        )
        print(
            f"Pivotal Z-Score:          {f.simulated_z_score_before:.2f} -> {f.simulated_z_score_after:.2f}"
        )
        print(f"Token Edit Rate:          {f.token_edit_rate * 100:.1f}%")
        print(
            f"4-gram Windows Broken:    {f.ngram_4_broken_ratio * 100:.1f}%"
        )
        print(f"Semantic Preservation:    {f.semantic_similarity * 100:.1f}%")
        print("-" * 72)
        print(result.output_text)


def _run_benchmark(text: str, preset: str, secret_key: str) -> int:
    """Embed a genuine textGrain watermark, detect it, attack it, and re-detect."""
    watermarked = TextGrainSimulator.embed_watermark(
        text,
        secret_key=secret_key,
        window_size=4,
        entropy_budget=0.90,
        inject_zero_width=True,
    )
    det_before = TextGrainSimulator.detect_watermark(watermarked, secret_key=secret_key, window_size=4)

    cfg = PipelineConfig.from_preset(preset)
    pipeline = AntiWatermarkPipeline(cfg)
    result = pipeline.process(watermarked, cfg)

    det_after = TextGrainSimulator.detect_watermark(result.output_text, secret_key=secret_key, window_size=4)

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        console.print(
            Panel.fit(
                f"[bold cyan]Live textGrain Attack Benchmark[/bold cyan] (Preset: [yellow]{preset}[/yellow], Key: `{secret_key}`)",
                border_style="cyan",
            )
        )
        t = Table(show_header=True, header_style="bold magenta")
        t.add_column("Detector Metric", style="bold")
        t.add_column("Watermarked Input (Before Attack)", justify="right")
        t.add_column("After anti-text-watermarks", justify="right")

        t.add_row("Combined Z-Score (Threshold=2.0)", f"[bold red]{det_before.combined_z_score:.3f}[/bold red]", f"[bold green]{det_after.combined_z_score:.3f}[/bold green]")
        t.add_row("Gumbel Sum-Test Z-Score", f"{det_before.gumbel_z_score:.3f}", f"{det_after.gumbel_z_score:.3f}")
        t.add_row("Green-List Z-Score", f"{det_before.green_z_score:.3f}", f"{det_after.green_z_score:.3f}")
        t.add_row("Green Token Fraction", f"{det_before.green_fraction * 100:.1f}%", f"{det_after.green_fraction * 100:.1f}%")
        t.add_row("One-Sided p-value", f"{det_before.p_value:.6f}", f"{det_after.p_value:.6f}")
        t.add_row("Detector Verdict", f"[red]{det_before.verdict}[/red]", f"[green]{det_after.verdict}[/green]")
        t.add_row("4-gram Context Hash Disruption", "0.0%", f"[cyan]{result.forensics.ngram_4_broken_ratio * 100:.1f}%[/cyan]")
        console.print(t)
        console.print(Panel(watermarked, title="[red]1. Watermarked Text (Embedded textGrain + Zero-Width)[/red]", border_style="red"))
        console.print(Panel(result.output_text, title="[green]2. Attacked Output (Watermark Neutralized)[/green]", border_style="green"))
    except ImportError:
        print(f"Before Z={det_before.combined_z_score:.3f} ({det_before.verdict})")
        print(f"After  Z={det_after.combined_z_score:.3f} ({det_after.verdict})")
        print(result.output_text)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anti-text-watermarks",
        description="Unified adversarial toolkit against OpenAI textGrain, Google SynthID-Text, Red-Green statistical watermarks, and hidden Unicode markers.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands (defaults to `clean` if omitted)")

    # Subcommand: clean
    clean_p = subparsers.add_parser("clean", help="Clean and disrupt watermarks in text or files")
    _add_clean_args(clean_p)

    # Subcommand: benchmark
    bench_p = subparsers.add_parser(
        "benchmark",
        help="Run a live simulation: embed a real textGrain watermark, run the statistical detector, attack it, and verify z-score collapse",
    )
    bench_p.add_argument("-t", "--text", type=str, default=DEFAULT_DEMO_TEXT, help="Sample text to watermark and attack")
    bench_p.add_argument("-p", "--preset", type=str, default="balanced", choices=["stealth", "balanced", "aggressive", "dipper", "backtranslate"])
    bench_p.add_argument("-k", "--key", type=str, default=TextGrainSimulator.DEFAULT_KEY, help="Secret key for simulated textGrain detector")

    # Subcommand: web
    web_p = subparsers.add_parser("web", help="Launch the interactive anti-text-watermarks Web Studio")
    web_p.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Loopback IPv4 address only (default: 127.0.0.1); use an authenticated HTTPS reverse proxy for remote access",
    )
    web_p.add_argument("--port", type=int, default=8765, help="Port number (default: 8765)")
    web_p.add_argument(
        "--trusted-origin",
        type=str,
        default=None,
        help="HTTPS origin forwarded by an authenticated reverse proxy",
    )
    web_p.add_argument(
        "--llm-allowed-origin",
        action="append",
        default=None,
        metavar="ORIGIN",
        help="Additional LLM endpoint origin allowed by Web Studio (repeatable)",
    )
    web_p.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")

    # Also allow top-level flags directly for convenience
    _add_clean_args(parser)
    return parser


def _add_clean_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-t", "--text", type=str, default=None, help="Input text string to process")
    parser.add_argument("-f", "--file", type=str, default=None, help="Path to input text/markdown file")
    parser.add_argument("-o", "--output", type=str, default=None, help="Path to write cleaned output file")
    parser.add_argument(
        "-p",
        "--preset",
        type=str,
        default="balanced",
        choices=["stealth", "balanced", "aggressive", "dipper", "backtranslate", "custom"],
        help="Adversarial pipeline preset (default: balanced)",
    )
    parser.add_argument("--edit-rate", type=float, default=None, help="Target high-entropy lexical edit ratio (e.g. 0.26)")
    parser.add_argument("--window-size", type=int, default=None, help="Assumed watermark n-gram context window h (default: 4)")
    parser.add_argument("--lex-diversity", type=int, default=None, help="DIPPER lexical diversity dial (0..100)")
    parser.add_argument("--order-diversity", type=int, default=None, help="DIPPER order diversity dial (0..100)")
    parser.add_argument("--enable-dipper", action="store_true", help="Enable Stage 3 DIPPER LLM paraphrasing")
    parser.add_argument("--enable-backtranslate", action="store_true", help="Enable Stage 4 Multi-Pivot Back-Translation")
    parser.add_argument("--llm-url", type=str, default=None, help="OpenAI-compatible or Ollama base URL")
    parser.add_argument("--llm-model", type=str, default=None, help="LLM model name for DIPPER/Back-translation")
    parser.add_argument("--llm-key", type=str, default=None, help="API key for remote LLM endpoint")
    parser.add_argument("--json", action="store_true", help="Output full PipelineResult as JSON")
    parser.add_argument("--quiet", action="store_true", help="Output only the cleaned text without forensics table")


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "web":
        from .web.server import run_web_server

        run_web_server(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            trusted_origin=args.trusted_origin,
            allowed_llm_origins=args.llm_allowed_origin,
        )
        return 0

    if args.command == "benchmark":
        return _run_benchmark(text=args.text, preset=args.preset, secret_key=args.key)

    # Resolve input text for `clean` (or default top-level invocation)
    input_text: Optional[str] = args.text
    if not input_text and args.file:
        input_text = pathlib.Path(args.file).read_text(encoding="utf-8")
    if not input_text and not sys.stdin.isatty():
        input_text = sys.stdin.read()
    if not input_text:
        input_text = DEFAULT_DEMO_TEXT

    overrides = {}
    if args.edit_rate is not None:
        overrides["target_edit_rate"] = args.edit_rate
    if args.window_size is not None:
        overrides["context_window_size"] = args.window_size
    if args.lex_diversity is not None:
        overrides["lex_diversity"] = args.lex_diversity
    if args.order_diversity is not None:
        overrides["order_diversity"] = args.order_diversity
    if args.enable_dipper:
        overrides["enable_dipper_llm"] = True
    if args.enable_backtranslate:
        overrides["enable_backtranslate"] = True
    if args.llm_url:
        overrides["llm_base_url"] = args.llm_url
    if args.llm_model:
        overrides["llm_model"] = args.llm_model
    if args.llm_key:
        overrides["llm_api_key"] = args.llm_key

    cfg = PipelineConfig.from_preset(args.preset, **overrides)
    pipeline = AntiWatermarkPipeline(cfg)
    result = pipeline.process(input_text, cfg)

    if args.output:
        pathlib.Path(args.output).write_text(result.output_text, encoding="utf-8")

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif args.quiet:
        print(result.output_text)
    else:
        _print_report(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
