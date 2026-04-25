"""Fusion-dataset baseline comparison helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import time
from typing import Any

from pydantic import BaseModel, Field

try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover - fallback when tqdm is unavailable
    tqdm = None

from app.datasets.source_registry import get_dataset_source_profile
from app.evaluation.baselines import (
    FusionDatasetBaselineSpec,
    build_fusion_dataset_baseline_specs,
    build_keyword_baseline_plan,
    build_keyword_baseline_selected_agents,
)
from app.evaluation.dataset_runner import (
    ACTIONABLE_DOMAINS,
    DatasetEvalRecord,
    DatasetEvalReport,
    DatasetEvalSummary,
    _build_summary,
    _parse_json_like,
    _precision_recall_f1,
    build_dataset_eval_report,
    build_home_state_from_snapshot,
    build_task_request_from_rows,
    infer_gold_agents,
    normalize_predicted_actions,
    normalize_target_actions,
)


class FusionBaselineResult(BaseModel):
    """One baseline entry in a fusion comparison report."""

    baseline_id: str
    year: int
    display_name: str
    execution_mode: str
    principle: str
    characteristics: list[str] = Field(default_factory=list)
    primary_memory_backend: str = "none"
    llm_enabled: bool = False
    is_reference: bool = False
    summary: DatasetEvalSummary


class FusionComparisonTableRow(BaseModel):
    """One compact row in the unified current-vs-baseline comparison table."""

    system_id: str
    display_name: str
    role: str
    year: int | None = None
    primary_memory_backend: str = "none"
    llm_enabled: bool = False
    sample_count: int
    execution_success_rate: float
    wakeup_agent_f1: float
    proposal_domain_f1: float
    proposal_action_f1: float
    final_domain_f1: float
    final_service_f1: float
    final_action_f1: float
    wakeup_agent_exact_match_rate: float
    final_domain_exact_match_rate: float
    final_action_exact_match_rate: float
    avg_latency_ms: float
    avg_conflict_count: float
    avg_selected_agent_count: float
    avg_predicted_action_count: float
    avg_gold_action_count: float
    avg_action_count_abs_error: float


class FusionBaselineComparisonReport(BaseModel):
    """Top-level fusion baseline comparison payload."""

    generated_at: str
    sample_count: int
    config: dict[str, Any]
    current_system: FusionComparisonTableRow
    baselines: list[FusionBaselineResult] = Field(default_factory=list)
    comparison_table: list[FusionComparisonTableRow] = Field(default_factory=list)
    comparison_table_markdown: str = ""
    best_by_metric: dict[str, str] = Field(default_factory=dict)


def _filter_fusion_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if get_dataset_source_profile(str(row.get("source_dataset") or "")).source_family != "web"
    ]


def _evaluate_rule_only_row(row: dict[str, Any]) -> DatasetEvalRecord:
    state_row = {
        "snapshot_ts": row.get("snapshot_ts"),
        "occupancy_status": row.get("occupancy_status"),
        "sensor_summary_json": row.get("sensor_summary_json"),
        "device_state_json": row.get("device_state_json"),
        "environment_json": row.get("environment_json"),
        "history_action_summary_json": row.get("history_action_summary_json"),
    }
    task_row = {
        "task_id": row.get("task_id"),
        "task_source": row.get("task_source"),
        "raw_text": row.get("raw_text"),
        "parsed_slots_json": row.get("parsed_slots_json"),
        "trigger_json": row.get("trigger_json"),
        "source_dataset": row.get("source_dataset"),
    }
    home_state = build_home_state_from_snapshot(state_row)
    task_request = build_task_request_from_rows(task_row, state_row)

    gold_target_actions = _parse_json_like(row.get("target_actions_json")) or []
    if not isinstance(gold_target_actions, list):
        gold_target_actions = []
    gold_norm = normalize_target_actions(gold_target_actions)
    gold_agents = infer_gold_agents(gold_target_actions, task_request.description)

    started_at = time.perf_counter()
    selected_agents = build_keyword_baseline_selected_agents(task_request.description, home_state)
    plan = build_keyword_baseline_plan(task_request.task_id, task_request.description, home_state)
    latency_ms = (time.perf_counter() - started_at) * 1000.0

    predicted_norm = normalize_predicted_actions(plan.selected_actions)
    agent_precision, agent_recall, agent_f1 = _precision_recall_f1(set(selected_agents), gold_agents)
    proposal_domain_precision, proposal_domain_recall, proposal_domain_f1 = _precision_recall_f1(predicted_norm["domains"], gold_norm["domains"])
    proposal_action_precision, proposal_action_recall, proposal_action_f1 = _precision_recall_f1(predicted_norm["actions"], gold_norm["actions"])
    final_domain_precision, final_domain_recall, final_domain_f1 = _precision_recall_f1(predicted_norm["domains"], gold_norm["domains"])
    final_service_precision, final_service_recall, final_service_f1 = _precision_recall_f1(predicted_norm["services"], gold_norm["services"])
    final_action_precision, final_action_recall, final_action_f1 = _precision_recall_f1(predicted_norm["actions"], gold_norm["actions"])

    return DatasetEvalRecord(
        sample_id=str(row["sample_id"]),
        source_dataset=str(row.get("source_dataset") or "unknown"),
        task_source=str(row.get("task_source") or "unknown"),
        label_quality=str(row.get("label_quality") or "unknown"),
        gold_action_count=len(gold_target_actions),
        predicted_action_count=len(plan.selected_actions),
        proposal_action_count=len(plan.selected_actions),
        selected_agent_count=len(selected_agents),
        discussion_turn_count=0,
        conflict_count=0,
        execution_success=True,
        latency_ms=round(latency_ms, 3),
        wakeup_agent_precision=agent_precision,
        wakeup_agent_recall=agent_recall,
        wakeup_agent_f1=agent_f1,
        wakeup_agent_exact_match=set(selected_agents) == gold_agents,
        proposal_domain_precision=proposal_domain_precision,
        proposal_domain_recall=proposal_domain_recall,
        proposal_domain_f1=proposal_domain_f1,
        proposal_action_precision=proposal_action_precision,
        proposal_action_recall=proposal_action_recall,
        proposal_action_f1=proposal_action_f1,
        final_domain_precision=final_domain_precision,
        final_domain_recall=final_domain_recall,
        final_domain_f1=final_domain_f1,
        final_service_precision=final_service_precision,
        final_service_recall=final_service_recall,
        final_service_f1=final_service_f1,
        final_action_precision=final_action_precision,
        final_action_recall=final_action_recall,
        final_action_f1=final_action_f1,
        final_domain_exact_match=predicted_norm["domains"] == gold_norm["domains"],
        final_action_exact_match=predicted_norm["actions"] == gold_norm["actions"],
        action_count_abs_error=abs(len(plan.selected_actions) - len(gold_target_actions)),
        selected_agents_json=selected_agents,
        gold_agents_json=sorted(gold_agents),
        predicted_domains_json=sorted(predicted_norm["domains"]),
        gold_domains_json=sorted(gold_norm["domains"]),
        web_metrics=None,
    )


def _build_rule_only_report(
    *,
    rows: list[dict[str, Any]],
    output_dir: Path,
    show_progress: bool = True,
    progress_desc: str = "Evaluate rule baseline",
) -> DatasetEvalReport:
    iterator = rows
    if show_progress and tqdm is not None:
        iterator = tqdm(rows, desc=progress_desc, total=len(rows), unit="sample", dynamic_ncols=True)
    records = [_evaluate_rule_only_row(row) for row in iterator]
    by_source: dict[str, list[DatasetEvalRecord]] = defaultdict(list)
    by_task_source: dict[str, list[DatasetEvalRecord]] = defaultdict(list)
    by_label_quality: dict[str, list[DatasetEvalRecord]] = defaultdict(list)
    for record in records:
        by_source[record.source_dataset].append(record)
        by_task_source[record.task_source].append(record)
        by_label_quality[record.label_quality].append(record)

    return DatasetEvalReport(
        generated_at=datetime.now().isoformat(),
        config={
            "baseline_id": "rule_keyword",
            "primary_memory_backend": "none",
            "llm_enabled": False,
            "output_dir": str(output_dir),
            "sample_count": len(rows),
        },
        summary=_build_summary(records),
        web_summary=None,
        by_source_dataset={key: _build_summary(value) for key, value in by_source.items()},
        by_task_source={key: _build_summary(value) for key, value in by_task_source.items()},
        by_label_quality={key: _build_summary(value) for key, value in by_label_quality.items()},
        web_by_source_dataset={},
        records=records,
    )


def _summary_to_comparison_row(
    *,
    system_id: str,
    display_name: str,
    role: str,
    summary: DatasetEvalSummary,
    primary_memory_backend: str,
    llm_enabled: bool,
    year: int | None = None,
) -> FusionComparisonTableRow:
    return FusionComparisonTableRow(
        system_id=system_id,
        display_name=display_name,
        role=role,
        year=year,
        primary_memory_backend=primary_memory_backend,
        llm_enabled=llm_enabled,
        sample_count=summary.sample_count,
        execution_success_rate=summary.execution_success_rate,
        wakeup_agent_f1=summary.wakeup_agent_f1,
        proposal_domain_f1=summary.proposal_domain_f1,
        proposal_action_f1=summary.proposal_action_f1,
        final_domain_f1=summary.final_domain_f1,
        final_service_f1=summary.final_service_f1,
        final_action_f1=summary.final_action_f1,
        wakeup_agent_exact_match_rate=summary.wakeup_agent_exact_match_rate,
        final_domain_exact_match_rate=summary.final_domain_exact_match_rate,
        final_action_exact_match_rate=summary.final_action_exact_match_rate,
        avg_latency_ms=summary.avg_latency_ms,
        avg_conflict_count=summary.avg_conflict_count,
        avg_selected_agent_count=summary.avg_selected_agent_count,
        avg_predicted_action_count=summary.avg_predicted_action_count,
        avg_gold_action_count=summary.avg_gold_action_count,
        avg_action_count_abs_error=summary.avg_action_count_abs_error,
    )


def _render_comparison_table_markdown(rows: list[FusionComparisonTableRow]) -> str:
    if not rows:
        return ""

    headers = [
        "system_id",
        "display_name",
        "role",
        "year",
        "memory",
        "llm",
        "sample_count",
        "exec_success",
        "wakeup_f1",
        "proposal_domain_f1",
        "proposal_action_f1",
        "final_domain_f1",
        "final_service_f1",
        "final_action_f1",
        "wakeup_agent_em",
        "final_domain_em",
        "final_action_em",
        "latency_ms",
        "conflicts",
        "selected_agents",
        "predicted_actions",
        "gold_actions",
        "action_count_error",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.system_id,
                    row.display_name,
                    row.role,
                    str(row.year) if row.year is not None else "",
                    row.primary_memory_backend,
                    str(row.llm_enabled).lower(),
                    str(row.sample_count),
                    f"{row.execution_success_rate:.4f}",
                    f"{row.wakeup_agent_f1:.4f}",
                    f"{row.proposal_domain_f1:.4f}",
                    f"{row.proposal_action_f1:.4f}",
                    f"{row.final_domain_f1:.4f}",
                    f"{row.final_service_f1:.4f}",
                    f"{row.final_action_f1:.4f}",
                    f"{row.wakeup_agent_exact_match_rate:.4f}",
                    f"{row.final_domain_exact_match_rate:.4f}",
                    f"{row.final_action_exact_match_rate:.4f}",
                    f"{row.avg_latency_ms:.4f}",
                    f"{row.avg_conflict_count:.4f}",
                    f"{row.avg_selected_agent_count:.4f}",
                    f"{row.avg_predicted_action_count:.4f}",
                    f"{row.avg_gold_action_count:.4f}",
                    f"{row.avg_action_count_abs_error:.4f}",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _best_baseline_by_metric(rows: list[FusionComparisonTableRow]) -> dict[str, str]:
    if not rows:
        return {}

    metrics_higher_better = {
        "execution_success_rate",
        "wakeup_agent_f1",
        "proposal_domain_f1",
        "proposal_action_f1",
        "final_domain_f1",
        "final_service_f1",
        "final_action_f1",
        "wakeup_agent_exact_match_rate",
        "final_domain_exact_match_rate",
        "final_action_exact_match_rate",
    }
    metrics_lower_better = {
        "avg_latency_ms",
        "avg_conflict_count",
        "avg_selected_agent_count",
        "avg_predicted_action_count",
        "avg_gold_action_count",
        "avg_action_count_abs_error",
    }

    best: dict[str, str] = {}
    for metric in metrics_higher_better:
        winner = max(rows, key=lambda item: getattr(item, metric))
        best[metric] = winner.system_id
    for metric in metrics_lower_better:
        winner = min(rows, key=lambda item: getattr(item, metric))
        best[metric] = winner.system_id
    return best


def build_fusion_baseline_comparison_report(
    *,
    rows: list[dict[str, Any]],
    output_dir: Path,
    baseline_ids: list[str] | None = None,
    current_primary_memory_backend: str = "hybrid",
    llm_enabled: bool = False,
    show_progress: bool = True,
) -> FusionBaselineComparisonReport:
    """Compare runnable baselines on fusion-only rows using the existing metric surface."""

    fusion_rows = _filter_fusion_rows(rows)
    total_steps = 1 + len(selected_specs := (
        [spec for spec in build_fusion_dataset_baseline_specs() if not baseline_ids or spec.baseline_id in set(baseline_ids)]
    ))
    progress = None
    if show_progress and tqdm is not None:
        progress = tqdm(total=total_steps, desc="Fusion baseline comparison", unit="system", dynamic_ncols=True)

    current_label = f"current_system ({current_primary_memory_backend})"
    if progress is not None:
        progress.set_postfix_str(current_label)
    current_report = build_dataset_eval_report(
        rows=fusion_rows,
        output_dir=output_dir / "current_system",
        primary_memory_backend=current_primary_memory_backend,
        llm_enabled=llm_enabled,
        show_progress=show_progress,
    )
    if progress is not None:
        progress.update(1)
    current_system = _summary_to_comparison_row(
        system_id="current_system",
        display_name="Current Program",
        role="current",
        summary=current_report.summary,
        primary_memory_backend=current_primary_memory_backend,
        llm_enabled=llm_enabled,
    )

    baseline_results: list[FusionBaselineResult] = []
    for spec in selected_specs:
        baseline_output_dir = output_dir / spec.baseline_id
        if progress is not None:
            progress.set_postfix_str(spec.baseline_id)
        if spec.execution_mode == "rule_only":
            report = _build_rule_only_report(
                rows=fusion_rows,
                output_dir=baseline_output_dir,
                show_progress=show_progress,
                progress_desc=f"Evaluate {spec.baseline_id}",
            )
        else:
            report = build_dataset_eval_report(
                rows=fusion_rows,
                output_dir=baseline_output_dir,
                primary_memory_backend=spec.primary_memory_backend,
                llm_enabled=llm_enabled or spec.llm_enabled,
                show_progress=show_progress,
            )
        if progress is not None:
            progress.update(1)
        baseline_results.append(
            FusionBaselineResult(
                baseline_id=spec.baseline_id,
                year=spec.year,
                display_name=spec.display_name,
                execution_mode=spec.execution_mode,
                principle=spec.principle,
                characteristics=spec.characteristics,
                primary_memory_backend=spec.primary_memory_backend,
                llm_enabled=llm_enabled or spec.llm_enabled,
                is_reference=spec.is_reference,
                summary=report.summary,
            )
        )

    comparison_table = [current_system]
    comparison_table.extend(
        _summary_to_comparison_row(
            system_id=baseline.baseline_id,
            display_name=baseline.display_name,
            role="baseline",
            year=baseline.year,
            summary=baseline.summary,
            primary_memory_backend=baseline.primary_memory_backend,
            llm_enabled=baseline.llm_enabled,
        )
        for baseline in baseline_results
    )
    if progress is not None:
        progress.close()

    return FusionBaselineComparisonReport(
        generated_at=datetime.now().isoformat(),
        sample_count=len(fusion_rows),
        config={
            "requested_baselines": baseline_ids or [spec.baseline_id for spec in selected_specs],
            "current_primary_memory_backend": current_primary_memory_backend,
            "llm_enabled": llm_enabled,
            "output_dir": str(output_dir),
            "actionable_domains": sorted(ACTIONABLE_DOMAINS),
        },
        current_system=current_system,
        baselines=baseline_results,
        comparison_table=comparison_table,
        comparison_table_markdown=_render_comparison_table_markdown(comparison_table),
        best_by_metric=_best_baseline_by_metric(comparison_table),
    )
