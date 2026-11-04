document.addEventListener("DOMContentLoaded", () => {
  const inputText = document.getElementById("input-text");
  const outputText = document.getElementById("output-text");
  const presetSelect = document.getElementById("preset-select");
  const sliderEditRate = document.getElementById("slider-edit-rate");
  const lblEditRate = document.getElementById("lbl-edit-rate");
  const sliderWindowSize = document.getElementById("slider-window-size");
  const lblWindowSize = document.getElementById("lbl-window-size");
  const sliderLexDiv = document.getElementById("slider-lex-div");
  const lblLexDiv = document.getElementById("lbl-lex-div");
  const sliderOrderDiv = document.getElementById("slider-order-div");
  const lblOrderDiv = document.getElementById("lbl-order-div");

  const chkSanitizer = document.getElementById("chk-sanitizer");
  const chkSyntax = document.getElementById("chk-syntax");
  const chkCliches = document.getElementById("chk-cliches");
  const chkGuard = document.getElementById("chk-guard");
  const chkDipper = document.getElementById("chk-dipper");
  const chkBt = document.getElementById("chk-bt");

  const inputLlmUrl = document.getElementById("input-llm-url");
  const inputLlmModel = document.getElementById("input-llm-model");
  const inputLlmKey = document.getElementById("input-llm-key");

  // Mode Tabs
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });

  // Output View Switcher
  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-view]").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".output-view").forEach((v) => v.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`view-${btn.dataset.view}`).classList.add("active");
    });
  });

  // Preset Synchronizer
  presetSelect.addEventListener("change", () => {
    const p = presetSelect.value;
    if (p === "stealth") {
      sliderEditRate.value = 14;
      chkSyntax.checked = false;
      chkDipper.checked = false;
      chkBt.checked = false;
    } else if (p === "balanced") {
      sliderEditRate.value = 26;
      chkSyntax.checked = true;
      chkDipper.checked = false;
      chkBt.checked = false;
    } else if (p === "aggressive") {
      sliderEditRate.value = 42;
      chkSyntax.checked = true;
      chkDipper.checked = false;
      chkBt.checked = false;
    } else if (p === "dipper") {
      sliderEditRate.value = 24;
      chkSyntax.checked = true;
      chkDipper.checked = true;
      chkBt.checked = false;
    } else if (p === "backtranslate") {
      sliderEditRate.value = 22;
      chkSyntax.checked = true;
      chkDipper.checked = false;
      chkBt.checked = true;
    }
    lblEditRate.textContent = `${sliderEditRate.value}%`;
  });

  sliderEditRate.addEventListener("input", () => {
    lblEditRate.textContent = `${sliderEditRate.value}%`;
  });
  sliderWindowSize.addEventListener("input", () => {
    lblWindowSize.textContent = `${sliderWindowSize.value} tokens`;
  });
  sliderLexDiv.addEventListener("input", () => {
    lblLexDiv.textContent = sliderLexDiv.value;
  });
  sliderOrderDiv.addEventListener("input", () => {
    lblOrderDiv.textContent = sliderOrderDiv.value;
  });

  // Load Demo Text
  async function loadDemoText() {
    try {
      const res = await fetch("/api/demo");
      const data = await res.json();
      inputText.value = data.demo_text || "";
    } catch (e) {
      console.error(e);
    }
  }

  document.getElementById("btn-load-demo").addEventListener("click", async () => {
    await loadDemoText();
    runPipeline();
  });

  document.getElementById("btn-clear").addEventListener("click", () => {
    inputText.value = "";
    outputText.value = "";
  });

  // Inject Zero-Width & Homoglyph Watermark for testing
  document.getElementById("btn-inject-zw").addEventListener("click", () => {
    if (!inputText.value.trim()) return;
    const chars = Array.from(inputText.value);
    const out = [];
    chars.forEach((ch, idx) => {
      out.push(ch);
      if (idx % 12 === 5) out.push("\u200B"); // Zero-width space
      if (idx % 19 === 3) out.push("\u200D"); // Zero-width joiner
    });
    inputText.value = out.join("");
    runPipeline();
  });

  // Copy Result
  document.getElementById("btn-copy-output").addEventListener("click", async () => {
    const btn = document.getElementById("btn-copy-output");
    if (!outputText.value) return;
    await navigator.clipboard.writeText(outputText.value);
    const orig = btn.textContent;
    btn.textContent = "✅ 已复制!";
    setTimeout(() => (btn.textContent = orig), 1600);
  });

  // Execute Pipeline
  async function runPipeline() {
    const btn = document.getElementById("btn-run-pipeline");
    const raw = inputText.value;
    if (!raw.trim()) return;

    btn.disabled = true;
    const origBtnText = btn.textContent;
    btn.textContent = "⏳ 正在执行多级统计去水印与哈希破坏...";

    try {
      const payload = {
        text: raw,
        preset: presetSelect.value,
        enable_sanitizer: chkSanitizer.checked,
        protect_markdown: chkGuard.checked,
        enable_syntactic_shift: chkSyntax.checked,
        scrub_ai_cliches: chkCliches.checked,
        target_edit_rate: parseInt(sliderEditRate.value, 10) / 100.0,
        context_window_size: parseInt(sliderWindowSize.value, 10),
        enable_dipper_llm: chkDipper.checked,
        lex_diversity: parseInt(sliderLexDiv.value, 10),
        order_diversity: parseInt(sliderOrderDiv.value, 10),
        llm_base_url: inputLlmUrl.value.trim(),
        llm_model: inputLlmModel.value.trim(),
        llm_api_key: inputLlmKey.value.trim(),
        enable_backtranslate: chkBt.checked,
      };

      const res = await fetch("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      renderPipelineResult(result);
    } catch (err) {
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = origBtnText;
    }
  }

  function renderPipelineResult(result) {
    outputText.value = result.output_text || "";
    const f = result.forensics || {};
    const s = result.sanitizer_stats || {};
    const d = result.disruption_stats || {};

    // Warnings
    const warnBanner = document.getElementById("warnings-banner");
    if (result.warnings && result.warnings.length > 0) {
      warnBanner.textContent = "提示: " + result.warnings.join(" | ");
      warnBanner.classList.remove("hidden");
    } else {
      warnBanner.classList.add("hidden");
    }

    // Card 1: textGrain Survival
    const beforePct = ((f.estimated_textgrain_before || 0) * 100).toFixed(1);
    const afterPct = ((f.estimated_textgrain_after || 0) * 100).toFixed(1);
    document.getElementById("m-tg-before").textContent = `${beforePct}%`;
    document.getElementById("m-tg-after").textContent = `${afterPct}%`;
    document.getElementById("bar-tg-after").style.width = `${Math.min(100, afterPct)}%`;

    const tagSurv = document.getElementById("tag-survival");
    if (f.estimated_textgrain_after <= 0.20) {
      tagSurv.textContent = "✅ 统计显著性已击穿";
      tagSurv.className = "metric-tag tag-green";
    } else {
      tagSurv.textContent = "⚠️ 仍有残余偏置";
      tagSurv.className = "metric-tag tag-red";
    }

    // Card 2: Z-score
    document.getElementById("m-z-before").textContent = `Z=${(f.simulated_z_score_before || 0).toFixed(2)}`;
    document.getElementById("m-z-after").textContent = `Z=${(f.simulated_z_score_after || 0).toFixed(2)}`;
    document.getElementById("m-pvalue-foot").textContent =
      `p-value: ${(f.simulated_p_value_before || 0).toFixed(4)} → ${(f.simulated_p_value_after || 0).toFixed(4)}`;

    // Card 3: n-gram broken
    const ng4 = ((f.ngram_4_broken_ratio || 0) * 100).toFixed(1);
    const ng3 = ((f.ngram_3_broken_ratio || 0) * 100).toFixed(1);
    const ng5 = ((f.ngram_5_broken_ratio || 0) * 100).toFixed(1);
    document.getElementById("m-ngram4").textContent = `${ng4}%`;
    document.getElementById("bar-ngram4").style.width = `${Math.min(100, ng4)}%`;
    document.getElementById("m-ngram-detail").textContent = `3-gram 破坏: ${ng3}% | 5-gram 破坏: ${ng5}%`;

    // Card 4: Edit rate & Semantic score
    document.getElementById("m-edit-rate").textContent = `${((f.token_edit_rate || 0) * 100).toFixed(1)}%`;
    document.getElementById("m-sem-score").textContent = `保真 ${((f.semantic_similarity || 1) * 100).toFixed(1)}%`;
    const hiddenRemoved = (s.zero_width_removed || 0) + (s.tag_chars_removed || 0) + (s.homoglyphs_normalized || 0);
    document.getElementById("m-unicode-foot").textContent =
      `隐形符号清除: ${hiddenRemoved} | 句式倒装: ${d.clauses_reordered || 0} | 代码锁定: ${s.protected_spans_count || 0}`;

    // Render Heatmap
    const hmBox = document.getElementById("heatmap-container");
    hmBox.innerHTML = "";
    (f.token_heatmap || []).forEach((item) => {
      const span = document.createElement("span");
      span.className = `hm-tok hm-status-${item.status}`;
      span.textContent = item.token;
      if (item.status === 2) span.title = "直接替换的高熵枢轴词 (Direct High-Entropy Pivot)";
      else if (item.status === 1) span.title = "受前序枢轴词影响，局部滑动窗口哈希已级联失效 (Context Hash Invalidated)";
      hmBox.appendChild(span);
    });

    // Render Diff
    const diffBox = document.getElementById("diff-container");
    diffBox.innerHTML = "";
    (result.diff_segments || []).forEach((seg) => {
      const span = document.createElement("span");
      if (seg.type === "delete") {
        span.className = "diff-del";
        span.textContent = seg.text;
      } else if (seg.type === "insert") {
        span.className = "diff-ins";
        span.textContent = seg.text;
      } else {
        span.textContent = seg.text;
      }
      diffBox.appendChild(span);
    });

    // Render Audit Log
    const auditBox = document.getElementById("audit-container");
    auditBox.innerHTML = "";
    const logs = d.replacements_log || [];
    if (s.details && s.details.length > 0) {
      s.details.forEach((detail) => {
        const row = document.createElement("div");
        row.className = "audit-item";
        row.innerHTML = `<span>🧹 ${escapeHtml(detail)}</span><span class="audit-badge">Stage 1 Sanitizer</span>`;
        auditBox.appendChild(row);
      });
    }
    logs.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "audit-item";
      row.innerHTML = `
        <span><del class="diff-del">${escapeHtml(entry.original)}</del> → <ins class="diff-ins">${escapeHtml(entry.replacement)}</ins></span>
        <span class="audit-badge">${escapeHtml(entry.type)}</span>
      `;
      auditBox.appendChild(row);
    });
  }

  // Live Sandbox Execution
  async function runSandbox() {
    const btn = document.getElementById("btn-run-sandbox");
    btn.disabled = true;
    const origLabel = btn.textContent;
    btn.textContent = "⏳ 正在嵌入 textGrain 信号并执行对抗击穿...";

    try {
      const res = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: inputText.value,
          secret_key: document.getElementById("sandbox-key").value.trim(),
          preset: document.getElementById("sandbox-preset").value,
          inject_zero_width: true,
        }),
      });
      const data = await res.json();
      const b = data.detection_before || {};
      const a = data.detection_after || {};

      document.getElementById("sb-verdict-before").textContent = b.verdict || "";
      document.getElementById("sb-z-before").textContent = (b.combined_z_score || 0).toFixed(3);
      document.getElementById("sb-gz-before").textContent = (b.gumbel_z_score || 0).toFixed(3);
      document.getElementById("sb-green-before").textContent = `${((b.green_fraction || 0) * 100).toFixed(1)}%`;
      document.getElementById("sb-p-before").textContent = (b.p_value || 0).toFixed(5);
      document.getElementById("sb-text-before").textContent = data.watermarked_text || "";

      document.getElementById("sb-verdict-after").textContent = a.verdict || "";
      document.getElementById("sb-z-after").textContent = (a.combined_z_score || 0).toFixed(3);
      document.getElementById("sb-gz-after").textContent = (a.gumbel_z_score || 0).toFixed(3);
      document.getElementById("sb-green-after").textContent = `${((a.green_fraction || 0) * 100).toFixed(1)}%`;
      document.getElementById("sb-p-after").textContent = (a.p_value || 0).toFixed(5);
      document.getElementById("sb-text-after").textContent = data.attacked_text || "";
    } catch (e) {
      console.error(e);
    } finally {
      btn.disabled = false;
      btn.textContent = origLabel;
    }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  document.getElementById("btn-run-pipeline").addEventListener("click", runPipeline);
  document.getElementById("btn-run-sandbox").addEventListener("click", runSandbox);

  // Initialize with demo text and run once
  loadDemoText().then(() => {
    runPipeline();
    runSandbox();
  });
});
