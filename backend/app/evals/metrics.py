"""客观文本指标（无外部依赖，纯文本输入）。

设计取向：
- 所有函数都接受字符串，不依赖任何 model/DB
- 每个指标返回简单 dict / float / list，便于 JSON 序列化
- 词典内置（感官词），不读取外部资源，保证 CI 可重现
"""
from __future__ import annotations

import re
from typing import Any

# 中英标点合一的句子结束符；用于切分句子做长度统计
_SENTENCE_SPLIT = re.compile(r"[。！？!?\.；;…]+")

# 段落以连续两个及以上换行分割（兼容 \r\n）
_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")

# 词汇切分：把中文按单字、英文/数字按词作为 token
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")

# 引号正则：英文双引号、中文弯引号、日式引号；
# 多语言成对引号都做最短匹配，避免吃掉跨段对话块
_QUOTE_PATTERNS = [
    re.compile(r'"([^"\n]+?)"'),
    re.compile(r"“([^”\n]+?)”"),
    re.compile(r"「([^」\n]+?)」"),
    re.compile(r"『([^』\n]+?)』"),
]

# 简易感官词词典（视/听/触/嗅/味）。
# 词典刻意精简：覆盖最常见的"画面感"指标词，避免过度膨胀。
# 后续可按 genre 扩展，但目前保持单一全局词典，KISS。
SENSORY_LEXICON: dict[str, tuple[str, ...]] = {
    "visual": (
        "看", "望", "瞥", "瞧", "凝视", "盯", "闪",
        "光", "影", "色", "亮", "暗", "雾", "烟",
    ),
    "auditory": (
        "听", "闻", "响", "声", "鸣", "喊", "呼",
        "低语", "尖叫", "轰鸣", "回荡", "嘶",
    ),
    "tactile": (
        "触", "摸", "抓", "握", "拍", "冷", "热", "烫",
        "粗糙", "光滑", "刺", "颤", "麻",
    ),
    "olfactory": (
        "嗅", "闻到", "气味", "香", "腥", "臭", "焦",
    ),
    "gustatory": (
        "尝", "品", "甜", "苦", "辣", "酸", "咸",
    ),
}


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text or "")]
    return [s for s in parts if s]


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


def sentence_length_stats(text: str) -> dict[str, float]:
    """句长统计：mean / variance / 句子数。

    句子按中英标点切分。长度按字符数计；中文 1 字 1 长度。
    """
    sentences = _split_sentences(text)
    if not sentences:
        return {"count": 0, "mean": 0.0, "variance": 0.0}
    lengths = [len(s) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return {
        "count": float(len(sentences)),
        "mean": round(mean, 3),
        "variance": round(variance, 3),
    }


def dialogue_ratio(text: str) -> float:
    """对话占比：引号包裹文本字符数 / 全文字符数。

    覆盖 "…" / “…” / 「…」 / 『…』 四种常见小说引号。
    引号内容会去重叠加，避免嵌套引号被重复计算。
    """
    if not text:
        return 0.0
    total = len(text)
    if total == 0:
        return 0.0
    # 标记每个字符是否落在任意引号内，避免多 pattern 重叠重复计数
    in_quote = [False] * total
    for pattern in _QUOTE_PATTERNS:
        for match in pattern.finditer(text):
            for idx in range(match.start(1), match.end(1)):
                if 0 <= idx < total:
                    in_quote[idx] = True
    dialog_chars = sum(1 for flag in in_quote if flag)
    return round(dialog_chars / total, 4)


def lexical_diversity(text: str) -> float:
    """词汇多样性：unique_tokens / total_tokens。

    中文按单字切分（粗糙但稳定），英文按词。
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    return round(len(set(tokens)) / len(tokens), 4)


def sensory_word_density(text: str) -> dict[str, float]:
    """感官词密度：各通道命中次数 / 全文 token 数，并给出 total。

    返回字段：visual / auditory / tactile / olfactory / gustatory / total。
    便于发现"全是对话/动作，缺少环境感官"的稿件。
    """
    tokens = _tokenize(text)
    if not tokens:
        return {key: 0.0 for key in (*SENSORY_LEXICON.keys(), "total")}
    total_tokens = len(tokens)
    out: dict[str, float] = {}
    total_hits = 0
    for channel, words in SENSORY_LEXICON.items():
        hits = 0
        for word in words:
            # 多字词直接计 substring 出现次数；单字词则在 token 序列里数
            if len(word) == 1:
                hits += sum(1 for tok in tokens if tok == word)
            else:
                hits += (text or "").count(word)
        out[channel] = round(hits / total_tokens, 4)
        total_hits += hits
    out["total"] = round(total_hits / total_tokens, 4)
    return out


def paragraph_length_distribution(text: str) -> list[int]:
    """段落长度分布：返回每段字符数的列表。

    便于发现"全是大段叙述"或"全是短段对话"的极端结构。
    """
    if not text:
        return []
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text)]
    return [len(p) for p in paragraphs if p]


def target_overshoot_ratio(text: str, target_words: int) -> float:
    """Sprint 16-E5：实际字数相对目标字数的偏差比例。

    返回 abs(len(text) - target) / max(target, 1)。
    - 0.0 = 完美命中
    - 0.15 = 偏差 15%（v2 prompt 容忍上限）
    - target<=0 时返 0（无目标无法对比）
    """
    if not target_words or target_words <= 0:
        return 0.0
    actual = len(text or "")
    return round(abs(actual - target_words) / max(1, target_words), 4)


def compute_all_metrics(text: str, *, target_words: int = 0) -> dict[str, Any]:
    """一次性跑齐全部客观指标，供 runner 使用。

    target_words 非零时附带 target_overshoot_ratio；为零时跳过该项。
    """
    metrics: dict[str, Any] = {
        "char_count": len(text or ""),
        "sentence_length": sentence_length_stats(text),
        "dialogue_ratio": dialogue_ratio(text),
        "lexical_diversity": lexical_diversity(text),
        "sensory_density": sensory_word_density(text),
        "paragraph_lengths": paragraph_length_distribution(text),
    }
    if target_words and target_words > 0:
        metrics["target_overshoot_ratio"] = target_overshoot_ratio(text, target_words)
    return metrics
