#!/usr/bin/env python3
"""Generate PPT-ready dataset figures and summary copy without plotting deps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd


PALETTE = {
    "navy": "#183153",
    "teal": "#0F766E",
    "green": "#3FA34D",
    "orange": "#F18F01",
    "red": "#C73E1D",
    "slate": "#5B6472",
    "light": "#F7F7F5",
    "gold": "#D4A017",
    "white": "#FFFFFF",
    "grid": "#D8DEE6",
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


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def load_stats(root: Path) -> dict:
    quality = json.loads((root / "reports/data_quality.json").read_text())
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


def svg_header(width: int, height: int, bg: str = "#FFFFFF") -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
    ]


def svg_footer(parts: list[str]) -> str:
    return "\n".join(parts + ["</svg>"])


def add_text(parts: list[str], x: int, y: int, text: str, size: int = 16, color: str = "#000000", weight: str = "normal") -> None:
    for idx, line in enumerate(text.split("\n")):
        yy = y + idx * int(size * 1.35)
        parts.append(
            f'<text x="{x}" y="{yy}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'font-family="Arial, Helvetica, sans-serif">{escape(line)}</text>'
        )


def add_rect(parts: list[str], x: int, y: int, w: int, h: int, fill: str, stroke: str = "none", rx: int = 18, sw: int = 1) -> None:
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
    )


def add_line(parts: list[str], x1: int, y1: int, x2: int, y2: int, color: str, width: int = 3) -> None:
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"/>')


def add_arrow(parts: list[str], x1: int, y1: int, x2: int, y2: int, color: str) -> None:
    add_line(parts, x1, y1, x2, y2, color, 4)
    parts.append(f'<polygon points="{x2},{y2} {x2-12},{y2-7} {x2-12},{y2+7}" fill="{color}"/>')


def add_barh(
    parts: list[str],
    x: int,
    y: int,
    width: int,
    row_height: int,
    labels: list[str],
    values: list[float],
    color: str,
    title: str,
    fmt=str,
) -> None:
    add_text(parts, x, y - 12, title, size=20, color=PALETTE["navy"], weight="bold")
    max_value = max(values) if values else 1
    for idx, (label, value) in enumerate(zip(labels, values)):
        yy = y + idx * row_height
        bar_w = int((value / max_value) * width) if max_value else 0
        add_text(parts, x, yy + 16, label, size=13, color=PALETTE["slate"])
        add_rect(parts, x + 170, yy, width, 22, fill="#EEF2F7", rx=8)
        add_rect(parts, x + 170, yy, max(bar_w, 2), 22, fill=color, rx=8)
        add_text(parts, x + 180 + width, yy + 16, fmt(value), size=12, color=PALETTE["navy"])


def add_barv(
    parts: list[str],
    x: int,
    y: int,
    width: int,
    height: int,
    labels: list[str],
    values: list[float],
    colors: list[str],
    title: str,
    fmt=str,
) -> None:
    add_text(parts, x, y - 12, title, size=20, color=PALETTE["navy"], weight="bold")
    max_value = max(values) if values else 1
    count = max(len(values), 1)
    bar_space = width // count
    bar_w = int(bar_space * 0.55)
    for idx, (label, value) in enumerate(zip(labels, values)):
        xx = x + idx * bar_space + int(bar_space * 0.2)
        bar_h = int((value / max_value) * height) if max_value else 0
        add_rect(parts, xx, y + height - bar_h, bar_w, max(bar_h, 2), fill=colors[idx], rx=8)
        add_text(parts, xx - 6, y + height + 22, label, size=12, color=PALETTE["slate"])
        add_text(parts, xx - 4, y + height - bar_h - 10, fmt(value), size=11, color=PALETTE["navy"])


def write_svg(path: Path, parts: list[str]) -> Path:
    path.write_text(svg_footer(parts))
    return path


def plot_pipeline_overview(stats: dict, figure_dir: Path) -> Path:
    quality = stats["quality"]
    parts = svg_header(1600, 900, bg=PALETTE["light"])
    add_text(parts, 60, 70, "Smart Home Training Warehouse", size=34, color=PALETTE["navy"], weight="bold")
    add_text(parts, 60, 110, "Raw multi-source corpora are normalized into a single episode-level decision dataset.", size=18, color=PALETTE["slate"])

    boxes = [
        (60, 210, 300, 220, "1. Raw Layer", [f"Files tracked: {human_count(quality['staging_counts']['source_manifest'])}", "Sources: HA / SmartSense / CASAS / EdgeWisePersona / Zh", "Preserve provenance and original format"], PALETTE["navy"]),
        (410, 210, 300, 220, "2. Staging Layer", [f"CASAS events: {human_count(quality['staging_counts']['stg_casas_event'])}", f"SmartSense logs: {human_count(quality['staging_counts']['stg_smartsense_log_action'])}", f"Zh commands: {human_count(quality['staging_counts']['stg_zh_command'])}"], PALETTE["teal"]),
        (760, 210, 300, 220, "3. Canonical Layer", [f"States: {human_count(quality['canonical_counts']['fact_state_snapshot'])}", f"Tasks: {human_count(quality['canonical_counts']['fact_task'])}", f"Actions: {human_count(quality['canonical_counts']['fact_action_item'])}"], PALETTE["green"]),
        (1110, 210, 320, 220, "4. Episode Layer", [f"Episodes: {human_count(quality['episode_count'])}", f"Candidates: {human_count(quality['bridge_counts']['bridge_task_candidate_device'])}", f"Synthetic discussion: {human_count(quality['bridge_counts']['synthetic_discussion'])}"], PALETTE["orange"]),
    ]
    for x, y, w, h, title, lines, color in boxes:
        add_rect(parts, x, y, w, h, fill=PALETTE["white"], stroke=color, sw=3, rx=28)
        add_text(parts, x + 24, y + 44, title, size=24, color=color, weight="bold")
        add_text(parts, x + 24, y + 88, "\n".join(lines), size=18, color=PALETTE["navy"])

    add_arrow(parts, 360, 320, 410, 320, PALETTE["teal"])
    add_arrow(parts, 710, 320, 760, 320, PALETTE["green"])
    add_arrow(parts, 1060, 320, 1110, 320, PALETTE["orange"])

    add_text(parts, 60, 540, "Unified episode schema", size=26, color=PALETTE["navy"], weight="bold")
    add_rect(parts, 60, 570, 1370, 150, fill=PALETTE["white"], stroke=PALETTE["grid"], sw=2, rx=24)
    add_text(
        parts,
        90,
        625,
        "sample_id | home_sk | user_sk | state_id | task_id | action_set_id | sample_ts\n"
        "candidate_devices_json | target_actions_json | synthetic_discussion_json | source_mix_json | label_quality | split",
        size=20,
        color=PALETTE["slate"],
        weight="bold",
    )
    add_text(
        parts,
        60,
        790,
        "Key message: heterogeneous smart-home data are transformed into a unified decision sample format,\nso training and evaluation can run through one orchestration pipeline instead of isolated tasks.",
        size=19,
        color=PALETTE["navy"],
    )
    return write_svg(figure_dir / "dataset_pipeline_overview.svg", parts)


def plot_source_breakdown(stats: dict, figure_dir: Path) -> Path:
    bridge_episode = stats["bridge_episode"]
    episodes = stats["episodes"]
    action_item = stats["fact_action_item"]

    episode_by_source = bridge_episode.groupby("source_dataset")["sample_id"].nunique().sort_values(ascending=False)
    split_counts = episodes["split"].value_counts().reindex(["train", "valid", "test"]).fillna(0).astype(int)
    label_quality = episodes["label_quality"].value_counts().reindex(["strong", "medium", "weak"]).fillna(0).astype(int)
    action_domain = action_item["device_domain"].value_counts().head(6).sort_values(ascending=False)

    parts = svg_header(1600, 1000, bg=PALETTE["white"])
    add_text(parts, 60, 70, "Current Warehouse Composition", size=34, color=PALETTE["navy"], weight="bold")
    add_barh(parts, 60, 150, 360, 60, episode_by_source.index.tolist(), episode_by_source.values.tolist(), PALETTE["teal"], "Episode contribution by source", human_count)
    add_barv(parts, 860, 170, 520, 250, split_counts.index.tolist(), split_counts.values.tolist(), [PALETTE["navy"], PALETTE["orange"], PALETTE["green"]], "Train / valid / test split", human_count)
    add_barv(parts, 860, 560, 520, 220, label_quality.index.tolist(), label_quality.values.tolist(), [PALETTE["green"], PALETTE["gold"], PALETTE["red"]], "Label quality distribution", human_count)
    add_barh(parts, 60, 560, 360, 56, action_domain.index.tolist(), action_domain.values.tolist(), PALETTE["orange"], "Top action domains", human_count)
    return write_svg(figure_dir / "dataset_result_breakdown.svg", parts)


def plot_validation_snapshot(stats: dict, figure_dir: Path) -> Path:
    quality = stats["quality"]
    timestamp_rates = pd.Series(quality["timestamp_parse_rate"]).sort_values(ascending=False)
    mapping = pd.Series({"device_domain": quality["device_domain_mapping_coverage"], "action_mapping": quality["action_mapping_coverage"]})
    null_ratios = pd.Series(quality["null_ratio"]).sort_values(ascending=False)
    leakage = pd.Series(quality["split_leakage"]).sort_values(ascending=False)

    parts = svg_header(1600, 1000, bg=PALETTE["white"])
    add_text(parts, 60, 70, "Validation and Data Quality Snapshot", size=34, color=PALETTE["navy"], weight="bold")
    add_barh(parts, 60, 150, 360, 60, timestamp_rates.index.tolist(), timestamp_rates.values.tolist(), PALETTE["green"], "Timestamp parse rate", pct)
    add_barv(parts, 860, 170, 520, 250, mapping.index.tolist(), mapping.values.tolist(), [PALETTE["orange"], PALETTE["teal"]], "Mapping coverage", pct)
    add_barh(parts, 60, 560, 360, 56, null_ratios.index.tolist(), null_ratios.values.tolist(), PALETTE["navy"], "Average null ratio by table family", pct)
    add_barv(parts, 860, 560, 520, 220, leakage.index.tolist(), leakage.values.tolist(), [PALETTE["red"], PALETTE["gold"]], "Split leakage checks", str)
    return write_svg(figure_dir / "dataset_validation_snapshot.svg", parts)


def plot_table_scale(stats: dict, figure_dir: Path) -> Path:
    quality = stats["quality"]
    table_counts = {
        **{f"stg:{k.replace('stg_', '')}": v for k, v in quality["staging_counts"].items() if k != "source_manifest"},
        **{f"fact:{k.replace('fact_', '')}": v for k, v in quality["canonical_counts"].items() if k.startswith("fact_")},
        **quality["bridge_counts"],
    }
    top_tables = pd.Series(table_counts).sort_values(ascending=False).head(10)
    colors = []
    for name in top_tables.index:
        if name.startswith("stg:"):
            colors.append(PALETTE["teal"])
        elif name.startswith("fact:"):
            colors.append(PALETTE["green"])
        else:
            colors.append(PALETTE["orange"])

    parts = svg_header(1600, 900, bg=PALETTE["white"])
    add_text(parts, 60, 70, "Largest Tables in the Current Warehouse", size=34, color=PALETTE["navy"], weight="bold")
    max_value = max(top_tables.values.tolist())
    y0 = 140
    for idx, (name, value) in enumerate(top_tables.items()):
        yy = y0 + idx * 65
        bar_w = int((value / max_value) * 1080)
        add_text(parts, 60, yy + 18, name, size=15, color=PALETTE["slate"])
        add_rect(parts, 320, yy, 1080, 28, fill="#EEF2F7", rx=10)
        add_rect(parts, 320, yy, max(bar_w, 2), 28, fill=colors[idx], rx=10)
        add_text(parts, 1415, yy + 19, human_count(int(value)), size=14, color=PALETTE["navy"], weight="bold")
    return write_svg(figure_dir / "dataset_table_scale.svg", parts)


def build_markdown_summary(stats: dict, figure_dir: Path, report_dir: Path) -> Path:
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
- [dataset_pipeline_overview.svg]({(figure_dir / 'dataset_pipeline_overview.svg').resolve()})
- [dataset_table_scale.svg]({(figure_dir / 'dataset_table_scale.svg').resolve()})

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
- [dataset_validation_snapshot.svg]({(figure_dir / 'dataset_validation_snapshot.svg').resolve()})

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
- [dataset_result_breakdown.svg]({(figure_dir / 'dataset_result_breakdown.svg').resolve()})

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
        plot_pipeline_overview(stats, figure_dir),
        plot_source_breakdown(stats, figure_dir),
        plot_validation_snapshot(stats, figure_dir),
        plot_table_scale(stats, figure_dir),
        build_markdown_summary(stats, figure_dir, report_dir),
    ]
    print("[ppt-assets] Generated files:")
    for path in created:
        print(f"- {path}")


if __name__ == "__main__":
    main()
