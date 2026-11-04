"""Bilingual (Chinese & English) High-Entropy Lexicon, AI-Cliché Scrubbers, and Syntactic Patterns.

Specifically targets high-conditional-entropy token positions where entropy-calibrated
watermarks (like OpenAI textGrain and Google SynthID-Text) concentrate their
Gumbel-max / Optimal-Transport probability shift.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# 1. AI-Cliché & High-Signature Phrase Scrubbers (Chinese & English)
# ---------------------------------------------------------------------------
ZH_AI_CLICHES: Dict[str, List[str]] = {
    "值得注意的是": ["需要指出的是", "应当留意", "有一点很关键", "不容忽视的是"],
    "综上所述": ["总体来看", "归结起来", "整体而言", "总括来说"],
    "总而言之": ["归根结底", "大体来说", "简言之", "概括来看"],
    "总而言之，": ["整体来说，", "归结起来，", "简言之，"],
    "不难发现": ["可以看出", "显而易见", "很容易察觉", "能够看到"],
    "显而易见": ["不言自明", "一目了然", "很清楚", "十分明确"],
    "在当今数字化时代": ["在当下的技术环境中", "随着数字技术普及", "在现今的信息社会里"],
    "在当今快节奏的社会中": ["在现代生活节奏下", "在当下的日常环境中"],
    "是一把双刃剑": ["既有优势也伴随隐患", "兼具利弊两面", "带来收益的同时也伴随风险"],
    "扮演着至关重要的角色": ["起着核心作用", "承担着关键职能", "发挥着举足轻重的作用"],
    "发挥着不可或缺的作用": ["起到关键支撑作用", "具有不可替代的价值", "承担着重要功能"],
    "不仅如此": ["在此之上", "而且", "更进一步看", "与此同时"],
    "与此同时": ["同一时间", "在此期间", "并且", "相伴而生的是"],
    "毋庸置疑": ["毫无疑问", "确凿无疑", "可以肯定", "无需多言"],
    "至关重要": ["极为关键", "举足轻重", "十分紧要", "尤为核心"],
    "不可或缺": ["必不可少", "极为必要", "难以替代", "至关重要"],
    "深入剖析": ["细致分析", "拆解探讨", "具体审视", "透彻研究"],
    "深入探讨": ["具体探讨", "细致分析", "深入研究", "详细讨论"],
    "提供了宝贵的见解": ["给出了有价值的参考", "带来了有益的启发", "提供了实用的视角"],
    "具有重要意义": ["具备相当高的价值", "影响深远", "很有现实分量"],
}

EN_AI_CLICHES: Dict[str, List[str]] = {
    "delve into": ["examine", "explore", "investigate", "analyze"],
    "delves into": ["examines", "explores", "investigates", "analyzes"],
    "delving into": ["examining", "exploring", "investigating", "analyzing"],
    "a testament to": ["clear evidence of", "a reflection of", "proof of", "an indicator of"],
    "rich tapestry": ["complex mix", "wide array", "diverse collection", "layered structure"],
    "tapestry of": ["combination of", "network of", "blend of", "mosaic of"],
    "it is important to note that": ["notably,", "keep in mind that", "importantly,", "worth noting is that"],
    "it is worth noting that": ["notably,", "specifically,", "interestingly,", "one key point is that"],
    "in conclusion,": ["to sum up,", "overall,", "ultimately,", "taken together,"],
    "in summary,": ["overall,", "briefly put,", "to recap,", "in short,"],
    "moreover,": ["beyond that,", "further,", "what is more,", "in addition,"],
    "furthermore,": ["in addition,", "beyond this,", "besides,", "equally important,"],
    "additionally,": ["also,", "alongside this,", "further,", "as well,"],
    "consequently,": ["as a result,", "hence,", "accordingly,", "for this reason,"],
    "nevertheless,": ["even so,", "still,", "nonetheless,", "all the same,"],
    "nonetheless,": ["even so,", "still,", "yet,", "despite that,"],
    "plays a crucial role": ["serves a key function", "is central", "acts as a vital factor", "matters greatly"],
    "plays a vital role": ["is essential", "serves an important purpose", "acts as a cornerstone"],
    "double-edged sword": ["mixed blessing", "source of both benefit and risk", "two-sided phenomenon"],
    "in today's fast-paced world": ["in modern life", "in the current environment", "nowadays"],
    "in the realm of": ["within", "in the field of", "across", "regarding"],
    "shed light on": ["clarify", "illuminate", "explain", "reveal"],
    "sheds light on": ["clarifies", "illuminates", "explains", "reveals"],
    "pave the way for": ["enable", "open the door to", "prepare the ground for", "facilitate"],
    "underscore the importance of": ["highlight the value of", "emphasize", "stress the need for"],
    "underscores the importance of": ["highlights the value of", "emphasizes", "stresses the need for"],
}

# ---------------------------------------------------------------------------
# 2. Chinese High-Entropy Equivalence Pools (Grouped for bidirectional lookup)
# ---------------------------------------------------------------------------
ZH_SYNONYM_CLUSTERS: List[List[str]] = [
    # Conjunctions & Discourse Transitions (Highest entropy in textGrain)
    ["然而", "不过", "只是", "话虽如此"],
    ["但是", "不过", "然而", "只是"],
    ["因此", "所以", "由此可见", "正因如此", "故而"],
    ["此外", "另外", "除此之外", "再者", "不仅如此"],
    ["首先", "第一", "起初", "先来看"],
    ["其次", "第二", "再者", "接着"],
    ["最后", "最终", "末了", "归结起来"],
    ["例如", "比如", "举例来说", "譬如"],
    ["尽管", "虽然", "纵使", "即便"],
    ["由于", "因为", "鉴于", "考虑到"],
    ["从而", "进而", "借此", "由此"],
    ["同时", "与此同时", "一并", "同步"],
    ["相反", "反之", "恰恰相反", "反过来"],
    ["实际上", "事实上", "其实", "严格来说"],
    ["通常", "往往", "一般而言", "大多时候"],
    ["尤其", "特别", "格外", "尤为"],
    ["几乎", "差不多", "近乎", "大体上"],
    ["迅速", "快速", "飞速", "很快地"],
    ["逐渐", "逐步", "慢慢", "渐次"],
    ["持续", "不断", "接连", "连续"],
    ["显著", "明显", "大幅", "突出"],
    ["极其", "十分", "非常", "相当", "极为"],
    ["大约", "大概", "约莫"],
    ["立即", "立刻", "马上", "当即"],
    ["完全", "彻底", "全面", "全然"],
    ["仅仅", "只是", "单单"],
    ["依然", "仍然", "依旧", "还是"],
    ["已经", "业已", "早已", "已然"],
    ["或许", "也许", "可能", "大概"],
    ["必须", "务必要", "一定要", "应当"],

    # High-Entropy Verbs
    ["表明", "显示", "说明", "印证", "反映出"],
    ["展示", "呈现", "展现", "体现", "显露"],
    ["促进", "推动", "带动", "助力", "加速"],
    ["提升", "提高", "增强", "改善", "优化"],
    ["降低", "减少", "削减", "缩减", "压低"],
    ["增加", "增长", "扩充", "提高", "增多"],
    ["改变", "调整", "转换", "重塑", "更动"],
    ["保持", "维持", "留存", "维系"],
    ["包含", "涵盖", "包括", "囊括", "涉及"],
    ["采用", "使用", "运用", "采取", "利用"],
    ["利用", "借助", "运用", "依托", "善用"],
    ["建立", "构建", "搭建", "确立", "形成"],
    ["实现", "达成", "完成", "促成"],
    ["提供", "给予", "供应", "带来", "赋予"],
    ["产生", "生成", "引发", "带来", "催生"],
    ["导致", "致使", "造成", "引起", "引发"],
    ["确保", "保证", "保障", "力保"],
    ["评估", "衡量", "测算", "评定", "审视"],
    ["验证", "检验", "核实", "印证", "证实"],
    ["消除", "清除", "抹除", "去除", "消解"],
    ["削弱", "淡化", "弱化", "减损", "冲淡"],
    ["破坏", "打乱", "瓦解", "扰乱", "损毁"],
    ["检测", "识别", "察觉", "测定", "探知"],
    ["依赖", "仰仗", "依靠", "取决于", "倚重"],
    ["认为", "主张", "判断", "看来"],
    ["发现", "察觉", "注意到", "观测到"],
    ["解决", "处理", "应对", "化解", "攻克"],
    ["面临", "遭遇", "面对", "碰到"],
    ["关注", "留意", "重视", "聚焦"],
    ["强调", "着重指出", "突显", "重申"],
    ["支持", "支撑", "扶持", "赞同"],
    ["影响", "左右", "波及", "作用于"],
    ["限制", "约束", "制约", "局限"],
    ["转换", "转化", "变成", "转为"],
    ["结合", "融合", "整合", "联结"],
    ["分析", "剖析", "解析", "研判"],
    ["设计", "规划", "构思", "定制"],
    ["调整", "调节", "修正", "微调"],
    ["保护", "守护", "维护", "保障"],
    ["引入", "带入", "注入", "加入"],

    # High-Entropy Adjectives & Nouns (including 4-char idioms as atomic units)
    ["至关重要", "极为关键", "举足轻重", "尤为核心"],
    ["不可或缺", "必不可少", "难以替代", "极为必要"],
    ["重要", "关键", "核心", "紧要"],
    ["主要", "首要", "核心", "关键"],
    ["基本", "基础", "根本", "大体"],
    ["复杂", "繁复", "棘手", "错综"],
    ["简单", "简易", "直接", "明了"],
    ["精确", "精准", "准确", "严密"],
    ["微弱", "细微", "轻微", "微小"],
    ["巨大", "庞大", "可观", "显著"],
    ["稳定", "稳固", "平稳", "可靠"],
    ["脆弱", "薄弱", "易损", "敏感"],
    ["特定", "指定", "专门", "具体"],
    ["普通", "常规", "一般", "常见"],
    ["不同", "各异", "有别", "相异"],
    ["相似", "类似", "相近", "雷同"],
    ["明显", "显著", "清晰", "突出"],
    ["潜在", "隐含", "背后", "暗藏"],
    ["有效", "行之有效", "管用", "切实"],
    ["完整", "完备", "健全", "周全"],
    ["原本", "原先", "最初", "原有"],
    ["方法", "方式", "途径", "手段", "策略"],
    ["机制", "机理", "原理", "运作方式"],
    ["特征", "特点", "特性", "属性"],
    ["优势", "长处", "强项", "益处"],
    ["缺陷", "局限", "短板", "不足"],
    ["结果", "成效", "成果", "结局"],
    ["趋势", "走向", "态势", "动向"],
    ["目标", "目的", "方向", "初衷"],
    ["问题", "难题", "症结", "挑战"],
    ["角度", "视角", "维度", "层面"],
    ["情况", "状况", "情形", "局面"],
    ["过程", "流程", "进程", "步骤"],
    ["领域", "范畴", "行业", "方向"],
]

# ---------------------------------------------------------------------------
# 3. English High-Entropy Equivalence Pools
# ---------------------------------------------------------------------------
EN_SYNONYM_CLUSTERS: List[List[str]] = [
    # Discourse & Transitions
    ["however", "nevertheless", "yet", "still", "even so"],
    ["therefore", "consequently", "thus", "accordingly", "hence"],
    ["furthermore", "moreover", "additionally", "besides", "further"],
    ["although", "even though", "while", "albeit"],
    ["because", "since", "as", "given that"],
    ["specifically", "particularly", "notably", "especially"],
    ["generally", "typically", "usually", "commonly", "ordinarily"],
    ["frequently", "often", "regularly", "repeatedly"],
    ["immediately", "instantly", "promptly", "right away"],
    ["gradually", "steadily", "progressively", "step by step"],
    ["significantly", "substantially", "considerably", "markedly", "notably"],
    ["completely", "entirely", "fully", "thoroughly", "wholly"],
    ["approximately", "roughly", "around", "nearly", "about"],
    ["extremely", "highly", "exceptionally", "remarkably", "exceedingly"],
    ["merely", "simply", "solely", "just", "only"],
    ["actually", "in fact", "indeed", "practically"],

    # High-Entropy Verbs (Base, 3rd-person singular, past, participle forms)
    ["demonstrate", "illustrate", "indicate", "show", "reveal"],
    ["demonstrates", "illustrates", "indicates", "shows", "reveals"],
    ["demonstrated", "illustrated", "indicated", "showed", "revealed"],
    ["utilize", "employ", "use", "apply", "adopt"],
    ["utilizes", "employs", "uses", "applies", "adopts"],
    ["utilized", "employed", "used", "applied", "adopted"],
    ["enhance", "improve", "strengthen", "boost", "refine"],
    ["enhances", "improves", "strengthens", "boosts", "refines"],
    ["enhanced", "improved", "strengthened", "boosted", "refined"],
    ["reduce", "decrease", "lower", "diminish", "curtail"],
    ["reduces", "decreases", "lowers", "diminishes", "curtails"],
    ["reduced", "decreased", "lowered", "diminished", "curtailed"],
    ["generate", "produce", "create", "yield", "form"],
    ["generates", "produces", "creates", "yields", "forms"],
    ["generated", "produced", "created", "yielded", "formed"],
    ["maintain", "preserve", "sustain", "retain", "keep"],
    ["maintains", "preserves", "sustains", "retains", "keeps"],
    ["maintained", "preserved", "sustained", "retained", "kept"],
    ["require", "need", "demand", "necessitate", "call for"],
    ["requires", "needs", "demands", "necessitates", "calls for"],
    ["required", "needed", "demanded", "necessitated"],
    ["provide", "offer", "supply", "deliver", "furnish"],
    ["provides", "offers", "supplies", "delivers", "furnishes"],
    ["provided", "offered", "supplied", "delivered"],
    ["ensure", "guarantee", "secure", "assure"],
    ["ensures", "guarantees", "secures", "assures"],
    ["evaluate", "assess", "examine", "analyze", "appraise"],
    ["evaluates", "assesses", "examines", "analyzes", "appraises"],
    ["evaluated", "assessed", "examined", "analyzed", "appraised"],
    ["modify", "alter", "adjust", "adapt", "revise"],
    ["modifies", "alters", "adjusts", "adapts", "revises"],
    ["modified", "altered", "adjusted", "adapted", "revised"],
    ["eliminate", "remove", "eradicate", "strip", "clear"],
    ["eliminates", "removes", "eradicates", "strips", "clears"],
    ["eliminated", "removed", "eradicated", "stripped", "cleared"],
    ["disrupt", "disturb", "break", "unsettle", "scramble"],
    ["disrupts", "disturbs", "breaks", "unsettles", "scrambles"],
    ["disrupted", "disturbed", "broken", "unsettled", "scrambled"],
    ["detect", "identify", "recognize", "spot", "discern"],
    ["detects", "identifies", "recognizes", "spots", "discerns"],
    ["detected", "identified", "recognized", "spotted", "discerned"],
    ["contain", "include", "comprise", "encompass", "incorporate"],
    ["contains", "includes", "comprises", "encompasses", "incorporates"],
    ["facilitate", "enable", "assist", "aid", "promote"],
    ["facilitates", "enables", "assists", "aids", "promotes"],
    ["establish", "build", "construct", "set up", "institute"],
    ["establishes", "builds", "constructs", "sets up", "institutes"],

    # High-Entropy Adjectives & Nouns
    ["important", "crucial", "vital", "essential", "critical", "key"],
    ["significant", "substantial", "notable", "considerable", "marked"],
    ["complex", "intricate", "complicated", "sophisticated", "elaborate"],
    ["simple", "straightforward", "basic", "uncomplicated", "direct"],
    ["accurate", "precise", "exact", "correct", "faithful"],
    ["effective", "efficient", "capable", "potent", "productive"],
    ["robust", "resilient", "durable", "sturdy", "strong"],
    ["fragile", "vulnerable", "delicate", "weak", "susceptible"],
    ["specific", "particular", "distinct", "definite", "concrete"],
    ["various", "diverse", "multiple", "numerous", "several"],
    ["different", "distinct", "varied", "divergent", "separate"],
    ["similar", "comparable", "akin", "analogous", "alike"],
    ["primary", "main", "principal", "chief", "foremost"],
    ["fundamental", "basic", "core", "underlying", "central"],
    ["rapid", "swift", "fast", "quick", "prompt"],
    ["subtle", "slight", "faint", "delicate", "nuanced"],
    ["comprehensive", "thorough", "extensive", "broad", "complete"],
    ["method", "approach", "technique", "strategy", "procedure"],
    ["methods", "approaches", "techniques", "strategies", "procedures"],
    ["mechanism", "process", "system", "framework", "structure"],
    ["feature", "characteristic", "attribute", "property", "trait"],
    ["features", "characteristics", "attributes", "properties", "traits"],
    ["advantage", "benefit", "strength", "merit", "upside"],
    ["advantages", "benefits", "strengths", "merits", "upsides"],
    ["limitation", "drawback", "weakness", "shortcoming", "constraint"],
    ["limitations", "drawbacks", "weaknesses", "shortcomings", "constraints"],
    ["result", "outcome", "consequence", "effect", "finding"],
    ["results", "outcomes", "consequences", "effects", "findings"],
    ["component", "element", "part", "module", "factor"],
    ["components", "elements", "parts", "modules", "factors"],
    ["objective", "goal", "aim", "target", "purpose"],
]


def _build_lookup_map(clusters: List[List[str]], case_insensitive: bool = False) -> Dict[str, List[str]]:
    lookup: Dict[str, List[str]] = {}
    for cluster in clusters:
        for word in cluster:
            key = word.lower() if case_insensitive else word
            alternatives = [w for w in cluster if (w.lower() if case_insensitive else w) != key]
            if key not in lookup:
                lookup[key] = alternatives
            else:
                for alt in alternatives:
                    if alt not in lookup[key]:
                        lookup[key].append(alt)
    return lookup


ZH_SYNONYM_MAP: Dict[str, List[str]] = _build_lookup_map(ZH_SYNONYM_CLUSTERS, case_insensitive=False)
EN_SYNONYM_MAP: Dict[str, List[str]] = _build_lookup_map(EN_SYNONYM_CLUSTERS, case_insensitive=True)

# Sorted Chinese lexicon keys (longest-first for maximal matching during segmentation)
ZH_LEXICON_KEYS_SORTED: List[str] = sorted(ZH_SYNONYM_MAP.keys(), key=len, reverse=True)

# ---------------------------------------------------------------------------
# 4. Syntactic Clause Transformation Rules (Voice / Order / Discourse Shift)
# ---------------------------------------------------------------------------
# Patterns that alter clause structure or functional particles to break n-gram order
ZH_SYNTACTIC_PATTERNS: List[Tuple[str, str, str]] = [
    # (Regex pattern, Replacement template, Description)
    (
        r"不仅([^，。；！？\n]{2,18})，而且([^，。；！？\n]{2,22})",
        r"除\1之外，还\2",
        "递进句式重构 (不仅...而且 -> 除...之外，还)",
    ),
    (
        r"虽然([^，。；！？\n]{2,18})，但是([^，。；！？\n]{2,22})",
        r"诚然\1，但\2",
        "让步转折重构 (虽然...但是 -> 诚然...但)",
    ),
    (
        r"尽管([^，。；！？\n]{2,18})，但([^，。；！？\n]{2,22})",
        r"即便\1，却依然\2",
        "让步句式重构 (尽管...但 -> 即便...却依然)",
    ),
    (
        r"因为([^，。；！？\n]{2,18})，所以([^，。；！？\n]{2,22})",
        r"之所以\2，是因为\1",
        "因果语序倒装 (因为A所以B -> 之所以B是因为A)",
    ),
    (
        r"由于([^，。；！？\n]{2,18})，因此([^，。；！？\n]{2,22})",
        r"鉴于\1，故而\2",
        "因果连词重构 (由于...因此 -> 鉴于...故而)",
    ),
    (
        r"如果([^，。；！？\n]{2,18})，那么(?:就)?([^，。；！？\n]{2,22})",
        r"倘若\1，便\2",
        "假设句式重构 (如果...那么 -> 倘若...便)",
    ),
    (
        r"只要([^，。；！？\n]{2,18})，就([^，。；！？\n]{2,22})",
        r"一旦\1，便\2",
        "条件句式重构 (只要...就 -> 一旦...便)",
    ),
    (
        r"通过([^，。；！？\n]{2,18})，我们可以([^，。；！？\n]{2,22})",
        r"借助\1，便能够\2",
        "方式状语重构 (通过...我们可以 -> 借助...便能够)",
    ),
    (
        r"为了([^，。；！？\n]{2,16})，([^，。；！？\n]{2,20})需要",
        r"出于\1的考量，\2应当",
        "目的状语重构 (为了...需要 -> 出于...的考量...应当)",
    ),
]

EN_SYNTACTIC_PATTERNS: List[Tuple[str, str, str]] = [
    (
        r"\bNot only does ([^,.;]{3,35}), but it also ([^,.;]{3,40})",
        r"Beyond \1, it further \2",
        "Correlative conjunction restructuring",
    ),
    (
        r"\bIn order to ([a-z]+\s+[^,.;]{3,35}),\s*",
        r"To \1, ",
        "Purpose infinitive tightening",
    ),
    (
        r"\bDue to the fact that ([^,.;]{3,40}),",
        r"Because \1,",
        "Subordinate clause streamlining",
    ),
    (
        r"\bDespite the fact that ([^,.;]{3,40}),",
        r"Even though \1,",
        "Concessive clause restructuring",
    ),
    (
        r"\bIt can be seen that ([^,.;]{3,45})",
        r"Evidently, \1",
        "Passive expletive elimination",
    ),
]
