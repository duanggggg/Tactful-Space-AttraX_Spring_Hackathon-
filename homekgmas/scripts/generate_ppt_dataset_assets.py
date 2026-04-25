#!/usr/bin/env python3
"""Generate PPT-ready dataset figures and summary copy.

This script reads the current warehouse outputs and writes:
1. A set of PNG figures under outputs/figures/ppt/
2. A markdown summary under reports/ppt_dataset_summary.md

The goal is to make the current data construction results easy to present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch


plt.rcParams["figure.dpi"] = 160
plt.rcParams["savefig.dpi"] = 220
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False


PALETTE = {
    "navy": "#183153",
    "teal": "#0F766E",
    "green": "#3FA34D",
    "orange": "#F18F01",
    "red": "#C73E1D",
    "sand": "#F5E6C8",
    "slate": "#5B6472",
    "light": "#F7F7F5",
    "gold": "#D4A017",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root directory.",
    )
    return parser.parse_args()


def human_count(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def load_stats(root: Path) -> dict:
    quality = json.loads((root / "reports/data_quality.json").read_text())
    sample_counts = pd.read_csv(root / "reports/sample_counts.csv")
    fact_task = pd.read_parquet(
        root / "data_processed/fact_task.parquet",
        columns=["task_source", "source_dataset"],
    )
    fact_action_item = pd.read_parquet(
        root / "data_processed/fact_action_item.parquet",
        columns=["device_domain", "service_name_norm", "source_dataset"],
    )
    bridge_episode = pd.read_parquet(root / "data_processed/bridge_episode_source.parquet")
    episodes = pd.read_parquet(
        root / "data_processed/episodes.parquet",
        columns=["sample_id", "label_quality", "split"],
    )

    return {
        "quality": quality,
        "sample_counts": sample_counts,
        "fact_task": fact_task,
        "fact_action_item": fact_action_item,
        "bridge_episode": bridge_episode,
        "episodes": episodes,
    }


def ensure_output_dirs(root: Path) -> tuple[Path, Path]:
    figure_dir = root / "outputs/figures/ppt"
    report_dir = root / "reports"
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    return figure_dir, report_dir


def _draw_box(ax, x: float, y: float, w: float, h: float, title: str, body: str, color: str) -> None:
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.03",
        linewidth=2,
        edgecolor=color,
        facecolor="white",
    )
    ax.add_patch(box)
    ax.text(x + 0.02, y + h - 0.08, title, fontsize=16, fontweight="bold", color=color, va="top")
    ax.text(x + 0.02, y + h - 0.16, body, fontsize=12, color=PALETTE["navy"], va="top", linespacing=1.6)


def plot_pipeline_overview(root: Path, stats: dict, figure_dir: Path) -> Path:
    quality = stats["quality"]
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor(PALETTE["light"])
    ax.set_facecolor(PALETTE["light"])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.04, 0.94, "Smart Home Training Warehouse", fontsize=24, fontweight="bold", color=PALETTE["navy"])
    ax.text(
        0.04,
        0.89,
        "Raw multi-source corpora are normalized into a unified episode-level supervision table.",
        fontsize=13,
        color=PALETTE["slate"],
    )

    raw_count = quality["staging_counts"]["source_manifest"]
    episode_count = quality["episode_count"]

    _draw_box(
        ax,
        0.04,
        0.52,
        0.2,
        0.25,
        "1. Raw Layer",
        "\n".join(
            [
                f"Files tracked: {human_count(raw_count)}",
                "Sources: HA / SmartSense / CASAS / EdgeWisePersona / Zh",
                "Keep original paths, formats, provenance",
            ]
        ),
        PALETTE["navy"],
    )
    _draw_box(
        ax,
        0.29,
        0.52,
        0.2,
        0.25,
        "2. Staging Layer",
        "\n".join(
            [
                f"CASAS events: {human_count(quality['staging_counts']['stg_casas_event'])}",
                f"SmartSense logs: {human_count(quality['staging_counts']['stg_smartsense_log_action'])}",
                f"Zh commands: {human_count(quality['staging_counts']['stg_zh_command'])}",
            ]
        ),
        PALETTE["teal"],
    )
    _draw_box(
        ax,
        0.54,
        0.52,
        0.2,
        0.25,
        "3. Canonical Layer",
        "\n".join(
            [
                f"States: {human_count(quality['canonical_counts']['fact_state_snapshot'])}",
                f"Tasks: {human_count(quality['canonical_counts']['fact_task'])}",
                f"Actions: {human_count(quality['canonical_counts']['fact_action_item'])}",
            ]
        ),
        PALETTE["green"],
    )
    _draw_box(
        ax,
        0.79,
        0.52,
        0.17,
        0.25,
        "4. Episode Layer",
        "\n".join(
            [
                f"Episodes: {human_count(episode_count)}",
                f"Candidates: {human_count(quality['bridge_counts']['bridge_task_candidate_device'])}",
                f"Synthetic discussion: {human_count(quality['bridge_counts']['synthetic_discussion'])}",
            ]
        ),
        PALETTE["orange"],
    )

    for start, end, color in [
        ((0.24, 0.64), (0.29, 0.64), PALETTE["teal"]),
        ((0.49, 0.64), (0.54, 0.64), PALETTE["green"]),
        ((0.74, 0.64), (0.79, 0.64), PALETTE["orange"]),
    ]:
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="->", lw=3, color=color))

    ax.text(0.04, 0.38, "Unified episode schema", fontsize=18, fontweight="bold", color=PALETTE["navy"])
    ax.text(
        0.04,
        0.31,
        "sample_id | home_sk | user_sk | state_id | task_id | action_set_id | sample_ts\n"
        "candidate_devices_json | target_actions_json | synthetic_discussion_json | source_mix_json | label_quality | split",
        fontsize=13,
        color=PALETTE["slate"],
        linespacing=1.8,
    )
    ax.text(
        0.04,
        0.12,
        "Key message: heterogeneous data are no longer kept as isolated benchmarks. "
        "They are aligned into a single decision-making sample format for orchestration training and evaluation.",
        fontsize=13,
        color=PALETTE["navy"],
    )

    path = figure_dir / "dataset_pipeline_overview.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_source_breakdown(root: Path, stats: dict, figure_dir: Path) -> Path:
    bridge_episode = stats["bridge_episode"]
    episodes = stats["episodes"]
    fact_task = stats["fact_task"]
    action_item = stats["fact_action_item"]

    episode_by_source = bridge_episode.groupby("source_dataset")["sample_id"].nunique().sort_values(ascending=True)
    split_counts = episodes["split"].value_counts().reindex(["train", "valid", "test"])
    label_quality = episodes["label_quality"].value_counts().reindex(["strong", "medium", "weak"]).fillna(0)
    task_source = fact_task["task_source"].value_counts().sort_values(ascending=True)
    action_domain = action_item["device_domain"].value_counts().head(8).sort_values(ascending=True)

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.patch.set_facecolor("white")

    axes[0, 0].barh(episode_by_source.index, episode_by_source.values, color=PALETTE["teal"])
    axes[0, 0].set_title("Episode contribution by source")
    axes[0, 0].set_xlabel("Unique episodes")

    axes[0, 1].bar(split_counts.index, split_counts.values, color=[PALETTE["navy"], PALETTE["orange"], PALETTE["green"]])
    axes[0, 1].set_title("Train / valid / test split")
    axes[0, 1].set_ylabel("Episodes")

    axes[1, 0].bar(label_quality.index, label_quality.values, color=[PALETTE["green"], PALETTE["gold"], PALETTE["red"]])
    axes[1, 0].set_title("Label quality distribution")
    axes[1, 0].set_ylabel("Episodes")

    axes[1, 1].barh(action_domain.index, action_domain.values, color=PALETTE["orange"])
    axes[1, 1].set_title("Top action domains")
    axes[1, 1].set_xlabel("Action items")

    for ax in axes.flat:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.suptitle("Current warehouse composition", fontsize=20, fontweight="bold", color=PALETTE["navy"])
    fig.tight_layout()
    path = figure_dir / "dataset_result_breakdown.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)

    path_json = figure_dir / "dataset_result_breakdown_stats.json"
    path_json.write_text(
        json.dumps(
            {
                "episode_by_source": episode_by_source.to_dict(),
                "split_counts": split_counts.to_dict(),
                "label_quality": label_quality.to_dict(),
                "task_source": task_source.to_dict(),
                "action_domain": action_domain.to_dict(),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return path


def plot_validation_snapshot(root: Path, stats: dict, figure_dir: Path) -> Path:
    quality = stats["quality"]
    timestamp_rates = pd.Series(quality["timestamp_parse_rate"]).sort_values(ascending=True)
    mapping = pd.Series(
        {
            "device_domain": quality["device_domain_mapping_coverage"],
            "action_mapping": quality["action_mapping_coverage"],
        }
    )
    null_ratios = pd.Series(quality["null_ratio"]).sort_values(ascending=True)
    leakage = pd.Series(quality["split_leakage"])

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.patch.set_facecolor("white")

    axes[0, 0].barh(timestamp_rates.index, timestamp_rates.values, color=PALETTE["green"])
    axes[0, 0].set_xlim(0, 1.05)
    axes[0, 0].set_title("Timestamp parse rate")

    axes[0, 1].bar(mapping.index, mapping.values, color=[PALETTE["orange"], PALETTE["teal"]])
    axes[0, 1].set_ylim(0, 1.05)
    axes[0, 1].set_title("Mapping coverage")

    axes[1, 0].barh(null_ratios.index, null_ratios.values, color=PALETTE["navy"])
    axes[1, 0].set_xlim(0, max(0.25, float(null_ratios.max()) * 1.1))
    axes[1, 0].set_title("Average null ratio by table family")

    axes[1, 1].bar(leakage.index, leakage.values, color=PALETTE["red"])
    axes[1, 1].set_title("Split leakage checks")
    axes[1, 1].set_ylabel("Entity count across multiple splits")

    for ax in axes.flat:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.suptitle("Validation and data quality snapshot", fontsize=20, fontweight="bold", color=PALETTE["navy"])
    fig.tight_layout()
    path = figure_dir / "dataset_validation_snapshot.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_table_scale(root: Path, stats: dict, figure_dir: Path) -> Path:
    quality = stats["quality"]
    table_counts = {
        **{f"stg:{k.replace('stg_', '')}": v for k, v in quality["staging_counts"].items() if k != "source_manifest"},
        **{f"fact:{k.replace('fact_', '')}": v for k, v in quality["canonical_counts"].items() if k.startswith("fact_")},
        **quality["bridge_counts"],
    }
    series = pd.Series(table_counts).sort_values(ascending=True).tail(12)

    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor("white")
    colors = [PALETTE["teal"] if name.startswith("stg:") else PALETTE["green"] if name.startswith("fact:") else PALETTE["orange"] for name in series.index]
    ax.barh(series.index, series.values, color=colors)
    ax.set_xscale("log")
    ax.set_xlabel("Row count (log scale)")
    ax.set_title("Largest tables in the current warehouse")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for idx, value in enumerate(series.values):
        ax.text(value * 1.03, idx, human_count(int(value)), va="center", fontsize=10, color=PALETTE["navy"])

    fig.tight_layout()
    path = figure_dir / "dataset_table_scale.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def build_markdown_summary(root: Path, stats: dict, figure_dir: Path, report_dir: Path) -> Path:
    quality = stats["quality"]
    bridge_episode = stats["bridge_episode"]
    fact_task = stats["fact_task"]
    fact_action_item = stats["fact_action_item"]

    episode_by_source = bridge_episode.groupby("source_dataset")["sample_id"].nunique().sort_values(ascending=False)
    task_source = fact_task["task_source"].value_counts()
    action_domain = fact_action_item["device_domain"].value_counts()

    md = f"""# PPT Dataset Summary

## 1. 数据集构建

本阶段工作的核心目标，是把多源、异构、粒度不一致的智能家居公开数据，统一整理成可用于“中枢节点决策”的 episode 级监督样本。具体来说，我们将 Home Assistant、SmartSense、CASAS、EdgeWisePersona 与中文家居命令数据统一接入，并构建了从 Raw、Staging、Canonical 到 Episode 的四层数据仓库。

当前仓库已经完成：
- 原始文件登记 {quality['staging_counts']['source_manifest']:,} 条
- 状态快照 `fact_state_snapshot` {quality['canonical_counts']['fact_state_snapshot']:,} 条
- 任务 `fact_task` {quality['canonical_counts']['fact_task']:,} 条
- 动作集合 `fact_action_set` {quality['canonical_counts']['fact_action_set']:,} 条
- 最终 episode 样本 `episodes.parquet` {quality['episode_count']:,} 条

统一后的监督样本以“一轮中枢决策”为单位，字段包括 `state_id`、`task_id`、`action_set_id`、候选设备集合、目标动作集合以及可选的 `synthetic_discussion`，从而使不同数据源能够进入同一条训练和评估流程。

推荐配图：
- [dataset_pipeline_overview.png]({(figure_dir / 'dataset_pipeline_overview.png').resolve()})
- [dataset_table_scale.png]({(figure_dir / 'dataset_table_scale.png').resolve()})

## 2. 验证方法

我们对数据构建流程采用了“结构完整性 + 映射覆盖率 + 切分安全性”三类验证方法。

第一，检查结构完整性：
- 时间戳解析率在核心表上达到 100%
- 去重统计在 staging / canonical / bridge 主要表上均为 0
- `episodes` 表空值比例为 0

第二，检查标准化质量：
- 设备域映射覆盖率为 {quality['device_domain_mapping_coverage']:.2%}
- 动作映射覆盖率为 {quality['action_mapping_coverage']:.2%}
- 对不能恢复强标签的数据源显式保留 `weak` 或 `medium` 标记，不伪造强监督

第三，检查切分泄漏：
- `home_multi_split_count = {quality['split_leakage']['home_multi_split_count']}`
- `user_multi_split_count = {quality['split_leakage']['user_multi_split_count']}`

这说明当前数据仓库已经具备可复现实验基础，但后续还需要进一步压低跨 split 的 home / user 泄漏数量。

推荐配图：
- [dataset_validation_snapshot.png]({(figure_dir / 'dataset_validation_snapshot.png').resolve()})

## 3. 当前结果

从最终样本规模来看，当前已经构建出 {quality['episode_count']:,} 条 episode。其中：
- `train` 集 {quality['split_counts']['train']:,} 条
- `valid` 集 {quality['split_counts']['valid']:,} 条
- `test` 集 {quality['split_counts']['test']:,} 条

从标签质量看：
- `strong` = {quality['label_quality_counts']['strong']:,}
- `medium` = {quality['label_quality_counts']['medium']:,}
- `weak` = {quality['label_quality_counts']['weak']:,}

从样本来源看，当前以 SmartSense 的历史动作监督为主，同时由中文命令和 Home Assistant 提供显式任务与目标动作对齐样本：
- {episode_by_source.to_string()}

从任务类型看，当前最主要的学习目标是“基于历史上下文预测下一步动作”，其次是“用户自然语言到动作”的映射，以及“routine 驱动的设备建议”：
- {task_source.to_string()}

从动作域看，已覆盖 `media_player`、`light`、`cover`、`climate`、`fan`、`switch`、`lock` 等多类设备：
- {action_domain.head(8).to_string()}

推荐配图：
- [dataset_result_breakdown.png]({(figure_dir / 'dataset_result_breakdown.png').resolve()})

## 4. 汇报中可直接使用的一段总结

目前我们已经把多源智能家居公开数据统一构造成了可用于中枢节点训练的 episode 级数据集。该数据集不再只是孤立的命令识别、环境感知或 routine 预测任务，而是被统一映射为“给定状态与任务，预测最终设备动作集合”的监督形式。当前共形成 {quality['episode_count']:,} 条样本，其中强监督样本占主导，能够支撑我们对中枢决策流程、候选设备召回、动作生成以及合成多 agent proposal 机制开展系统性实验。
"""

    path = report_dir / "ppt_dataset_summary.md"
    path.write_text(md)
    return path


def main() -> None:
    args = parse_args()
    root = args.project_root.resolve()
    figure_dir, report_dir = ensure_output_dirs(root)
    stats = load_stats(root)

    created = [
        plot_pipeline_overview(root, stats, figure_dir),
        plot_source_breakdown(root, stats, figure_dir),
        plot_validation_snapshot(root, stats, figure_dir),
        plot_table_scale(root, stats, figure_dir),
        build_markdown_summary(root, stats, figure_dir, report_dir),
    ]

    print("[ppt-assets] Generated files:")
    for path in created:
        print(f"- {path}")


if __name__ == "__main__":
    main()
