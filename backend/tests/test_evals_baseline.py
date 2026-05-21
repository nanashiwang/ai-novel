"""evals 基线：metrics 计算的回归测试 + 数据集可加载性。

不会调用 LLM；保证 CI 在无 API key 环境也能稳定通过。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.evals.metrics import (
    compute_all_metrics,
    dialogue_ratio,
    lexical_diversity,
    paragraph_length_distribution,
    sensory_word_density,
    sentence_length_stats,
)
from app.evals.runner import (
    DATASET_ROOT,
    list_dataset_paths,
    load_sample,
    run_eval_sync,
)

# ---- 基础 metric 单元测试 -----------------------------------------------


def test_sentence_length_stats_empty() -> None:
    stats = sentence_length_stats("")
    assert stats == {"count": 0, "mean": 0.0, "variance": 0.0}


def test_sentence_length_stats_basic() -> None:
    text = "他走进房间。她抬头。窗外有雨。"
    stats = sentence_length_stats(text)
    assert stats["count"] == 3
    assert stats["mean"] > 0


def test_dialogue_ratio_zero_for_pure_narration() -> None:
    assert dialogue_ratio("他走进房间，关上门。") == 0.0


def test_dialogue_ratio_detects_chinese_quotes() -> None:
    text = "他说：“你来了。”然后退后一步。"
    ratio = dialogue_ratio(text)
    # 引号内 3 字 / 全文 14 字 ≈ 0.21；只断言落在合理区间
    assert 0.15 <= ratio <= 0.35


def test_dialogue_ratio_handles_multiple_quote_styles() -> None:
    text = '"Hello" 「你好」 “OK”'
    ratio = dialogue_ratio(text)
    assert ratio > 0


def test_lexical_diversity_bounds() -> None:
    assert lexical_diversity("") == 0.0
    # 4 个 token 全为 "a"：unique/total = 1/4
    assert lexical_diversity("a a a a") == 0.25
    # 全独特词时应该接近 1
    assert lexical_diversity("abc def ghi") == 1.0


def test_sensory_density_returns_all_channels() -> None:
    out = sensory_word_density("他听见远处传来低语，看见雾里有光。")
    assert set(out.keys()) >= {"visual", "auditory", "tactile", "olfactory", "gustatory", "total"}
    assert out["auditory"] >= 0
    assert out["visual"] >= 0
    assert out["total"] >= out["visual"]


def test_paragraph_length_distribution() -> None:
    text = "第一段。\n\n第二段，稍长一点。\n\n第三段。"
    lens = paragraph_length_distribution(text)
    assert lens == [4, 9, 4]


def test_compute_all_metrics_smoke() -> None:
    result = compute_all_metrics("他笑了一下。“你来了。”窗外有雾。")
    assert result["char_count"] > 0
    assert "sentence_length" in result
    assert "dialogue_ratio" in result
    assert "lexical_diversity" in result
    assert "sensory_density" in result
    assert "paragraph_lengths" in result


# ---- 数据集 + runner 集成 -----------------------------------------------


def test_dataset_files_present() -> None:
    paths = list_dataset_paths("all")
    # Sprint 14-C1 要求至少 3 个数据集（玄幻/悬疑/言情）
    assert len(paths) >= 3
    ids = {p.stem for p in paths}
    assert {"xuanhuan_01", "mystery_01", "romance_01"} <= ids


def test_sample_loadable() -> None:
    path = DATASET_ROOT / "xuanhuan_01.yaml"
    sample = load_sample(path)
    assert sample.id == "xuanhuan_01"
    assert sample.genre
    assert sample.reference_content


def test_runner_metrics_within_reasonable_range(tmp_path: Path) -> None:
    """跑全部数据集（judge stub），保证指标计算无 regression。"""
    report = run_eval_sync(dataset="all", judge_disabled=True, output_dir=tmp_path)
    assert report.judge_disabled is True
    assert report.dataset_count >= 3
    assert report.samples
    # 所有样本对话比 / 词汇多样性都应在合理区间
    for sample in report.samples:
        objective = sample.objective_metrics
        assert 0.0 <= objective["dialogue_ratio"] <= 1.0
        assert 0.0 <= objective["lexical_diversity"] <= 1.0
        assert objective["char_count"] > 100  # 数据集正文不应过短
        sensory = objective["sensory_density"]
        assert 0.0 <= sensory["total"] <= 1.0
        # judge 走 stub 时所有维度=3.0
        assert sample.judge_scores["is_stub"] is True
        assert sample.judge_aggregate == pytest.approx(3.0)
    # aggregate 必须能 JSON 序列化
    payload = report.to_json()
    assert "samples" in payload
    # 报告文件应已写入 tmp_path
    assert any(tmp_path.glob("eval-*.json"))


def test_cli_help_does_not_crash() -> None:
    from app.evals import cli

    parser = cli._build_parser()
    # 触发 help 不抛
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
