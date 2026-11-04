# Attribution & Legal Notice (`anti-text-watermarks`)

**Original Author & Maintainer:** **01NGVI-QINGYI**  
**Official Repository:** https://github.com/01NGVI-QINGYI/anti-text-watermarks  
**Copyright:** Copyright (c) 2026 01NGVI-QINGYI. All rights reserved under the terms of the GNU Affero General Public License v3.0 (`AGPL-3.0-or-later`).

---

## 1. Mandatory Attribution & Modification Notice (AGPL-3.0 §4, §5, §7(b), §13)

Pursuant to **Sections 4, 5, 7(b), and 13 of the GNU Affero General Public License v3.0 (AGPL-3.0)**:

1. **Preservation of Original Authorship**: Any redistribution, fork, derivative work, package, or network service based on `anti-text-watermarks` **MUST** visibly retain the original author attribution (`By 01NGVI-QINGYI`) and a link to the official upstream repository (`https://github.com/01NGVI-QINGYI/anti-text-watermarks`) in its documentation, CLI output, and Web UI interface, and must include this `NOTICE.md` file intact.
2. **Prominent Notice of Modifications**: If you modify any file in this repository, you **MUST** add a prominent notice in the modified files stating that you changed the files and the date of the change, while preserving the original copyright notice of **01NGVI-QINGYI**.
3. **Network / SaaS Deployment Disclosure (AGPL-3.0 §13)**: If you deploy `anti-text-watermarks` (modified or unmodified) as a hosted web application, API, or online service, you **MUST** prominently display the original author credit (`01NGVI-QINGYI`) and provide users of that service direct, no-charge access to the complete Corresponding Source code under AGPL-3.0.

---

## 2. Upstream Concept & Research Acknowledgements

`anti-text-watermarks` is a clean-room implementation created from scratch using only the Python standard library. No third-party source code was copied verbatim. We gratefully acknowledge the following open-source projects and research papers whose mathematical concepts informed this architecture:

- **watermarks-remover** by Guillaume Meyer (`https://github.com/guillaumemeyer/watermarks-remover`)
- **remove-ai-watermarks** by wiltodelta (`https://github.com/wiltodelta/remove-ai-watermarks`, MIT)
- **DIPPER** by Kalpesh Krishna et al. (`https://github.com/martiansideofthemoon/ai-detection-paraphrases`, Apache-2.0)
- **MarkLLM** by THU-BPM (`https://github.com/THU-BPM/MarkLLM`, Apache-2.0)
- **Watermark Stealing / MIP** (`https://github.com/eth-sri/watermark-stealing` & `https://github.com/plll4zzx/mip_watermark_stealing`, MIT)
- **textGrain Technical Report** by OpenAI (*textGrain: Entropy-Calibrated Watermarking for Language Model Text*, 2026)

---

## 3. How to Cite

If you use, adapt, or benchmark against `anti-text-watermarks` in academic papers, technical blogs, or derivative software, please cite:

```bibtex
@software{qingyi2026antitextwatermarks,
  author       = {01NGVI-QINGYI},
  title        = {anti-text-watermarks: Adversarial Entropy-Calibrated De-Watermarking and Provenance Sanitization Engine},
  year         = {2026},
  version      = {1.0.0},
  license      = {AGPL-3.0-or-later},
  url          = {https://github.com/01NGVI-QINGYI/anti-text-watermarks}
}
```
