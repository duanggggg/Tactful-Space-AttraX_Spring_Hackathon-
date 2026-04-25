from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIGURE_DIR = PROJECT_ROOT / "outputs" / "figures" / "ppt"
CATALOG_PATH = FIGURE_DIR / "figure_catalog.json"

PALETTE = {
    "bg": "#FCFAF7",
    "panel": "#F3EEE8",
    "panel_alt": "#F8F6F2",
    "ink": "#3F4954",
    "muted": "#8A9199",
    "clay": "#B7A99A",
    "sage": "#7F8F84",
    "rose": "#B88C8C",
    "line": "#D8D1C7",
    "white": "#FFFFFF",
}

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def ensure_dirs() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    preferred = []
    for candidate in FONT_CANDIDATES:
        lower = candidate.lower()
        if bold and "bold" in lower:
            preferred.insert(0, candidate)
        elif not bold and "bold" not in lower:
            preferred.insert(0, candidate)
        else:
            preferred.append(candidate)
    for path in preferred:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


TITLE_FONT = load_font(42, bold=True)
SUBTITLE_FONT = load_font(22)
SECTION_FONT = load_font(28, bold=True)
BODY_FONT = load_font(20)
SMALL_FONT = load_font(17)
TINY_FONT = load_font(15)


def new_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), PALETTE["bg"])
    draw = ImageDraw.Draw(image)
    return image, draw


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            trial = word if not current else f"{current} {word}"
            width, _ = text_size(draw, trial, font)
            if width <= max_width or not current:
                current = trial
            else:
                lines.append(current.rstrip())
                current = word
        if current:
            lines.append(current.rstrip())
    return lines


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 6,
) -> int:
    lines = wrap_text(draw, text, font, max_width)
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        _, height = text_size(draw, line or "Ag", font)
        current_y += height + line_gap
    return current_y


def draw_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    body: str,
    face: str,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=24, fill=face, outline=PALETTE["line"], width=2)
    draw.text((x1 + 18, y1 + 16), title, font=SECTION_FONT, fill=PALETTE["ink"])
    draw_wrapped_text(
        draw,
        x1 + 18,
        y1 + 56,
        body,
        BODY_FONT,
        PALETTE["ink"],
        max_width=(x2 - x1 - 36),
        line_gap=4,
    )


def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color=None) -> None:
    color = color or PALETTE["muted"]
    draw.line([start, end], fill=color, width=4)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux = dx / length
    uy = dy / length
    px = -uy
    py = ux
    tip = end
    left = (int(end[0] - 18 * ux + 8 * px), int(end[1] - 18 * uy + 8 * py))
    right = (int(end[0] - 18 * ux - 8 * px), int(end[1] - 18 * uy - 8 * py))
    draw.polygon([tip, left, right], fill=color)


def draw_vertical_chart(
    draw: ImageDraw.ImageDraw,
    area: tuple[int, int, int, int],
    labels: list[str],
    values: list[float],
    colors: list[str],
    title: str,
    y_max: float | None = None,
) -> None:
    x1, y1, x2, y2 = area
    draw.text((x1, y1), title, font=SECTION_FONT, fill=PALETTE["ink"])
    chart_top = y1 + 48
    chart_bottom = y2 - 46
    chart_left = x1 + 30
    chart_right = x2 - 8
    draw.line((chart_left, chart_top, chart_left, chart_bottom), fill=PALETTE["line"], width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill=PALETTE["line"], width=2)
    max_value = max(values) if values else 1
    if y_max is not None:
        max_value = max(max_value, y_max)
    bar_width = max(28, int((chart_right - chart_left - 20) / max(len(values), 1) * 0.55))
    gap = int((chart_right - chart_left - (bar_width * len(values))) / max(len(values) + 1, 1))
    gap = max(gap, 10)
    for idx, value in enumerate(values):
        bar_x1 = chart_left + gap + idx * (bar_width + gap)
        bar_x2 = bar_x1 + bar_width
        usable_height = chart_bottom - chart_top - 18
        bar_height = int((value / max_value) * usable_height) if max_value else 0
        bar_y1 = chart_bottom - bar_height
        draw.rounded_rectangle((bar_x1, bar_y1, bar_x2, chart_bottom), radius=8, fill=colors[idx % len(colors)], outline=None)
        value_text = str(value)
        tw, th = text_size(draw, value_text, SMALL_FONT)
        draw.text((bar_x1 + (bar_width - tw) / 2, bar_y1 - th - 6), value_text, font=SMALL_FONT, fill=PALETTE["ink"])
        label = labels[idx]
        lw, _ = text_size(draw, label, TINY_FONT)
        draw.text((bar_x1 + (bar_width - lw) / 2, chart_bottom + 10), label, font=TINY_FONT, fill=PALETTE["muted"])


def draw_grouped_bar_chart(
    draw: ImageDraw.ImageDraw,
    area: tuple[int, int, int, int],
    labels: list[str],
    series: list[list[float]],
    series_names: list[str],
    colors: list[str],
    title: str,
) -> None:
    x1, y1, x2, y2 = area
    draw.text((x1, y1), title, font=SECTION_FONT, fill=PALETTE["ink"])
    chart_top = y1 + 52
    chart_bottom = y2 - 54
    chart_left = x1 + 34
    chart_right = x2 - 12
    draw.line((chart_left, chart_top, chart_left, chart_bottom), fill=PALETTE["line"], width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill=PALETTE["line"], width=2)
    max_value = max(max(values) for values in series) if series else 1
    group_width = int((chart_right - chart_left - 24) / max(len(labels), 1))
    bar_width = max(18, int(group_width / (len(series) + 1)))
    for idx, label in enumerate(labels):
        group_x = chart_left + 12 + idx * group_width
        for sidx, values in enumerate(series):
            value = values[idx]
            usable_height = chart_bottom - chart_top - 18
            bar_height = int((value / max_value) * usable_height) if max_value else 0
            bx1 = group_x + sidx * (bar_width + 6)
            bx2 = bx1 + bar_width
            by1 = chart_bottom - bar_height
            draw.rounded_rectangle((bx1, by1, bx2, chart_bottom), radius=6, fill=colors[sidx], outline=None)
            val = str(value)
            tw, th = text_size(draw, val, TINY_FONT)
            draw.text((bx1 + (bar_width - tw) / 2, by1 - th - 5), val, font=TINY_FONT, fill=PALETTE["ink"])
        lw, _ = text_size(draw, label, TINY_FONT)
        draw.text((group_x + (group_width - lw) / 2, chart_bottom + 10), label, font=TINY_FONT, fill=PALETTE["muted"])

    legend_x = x2 - 170
    legend_y = y1 + 8
    for idx, name in enumerate(series_names):
        ly = legend_y + idx * 24
        draw.rounded_rectangle((legend_x, ly + 4, legend_x + 16, ly + 18), radius=4, fill=colors[idx], outline=None)
        draw.text((legend_x + 24, ly), name, font=SMALL_FONT, fill=PALETTE["muted"])


def draw_horizontal_bars(
    draw: ImageDraw.ImageDraw,
    area: tuple[int, int, int, int],
    labels: list[str],
    values: list[float],
    color: str,
    title: str,
) -> None:
    x1, y1, x2, y2 = area
    draw.text((x1, y1), title, font=SECTION_FONT, fill=PALETTE["ink"])
    chart_left = x1 + 170
    chart_right = x2 - 10
    chart_top = y1 + 56
    row_gap = max(34, int((y2 - chart_top - 10) / max(len(labels), 1)))
    max_value = max(values) if values else 1
    for idx, (label, value) in enumerate(zip(labels, values)):
        y = chart_top + idx * row_gap
        draw.text((x1, y), label, font=TINY_FONT, fill=PALETTE["muted"])
        draw.rounded_rectangle((chart_left, y + 4, chart_right, y + 20), radius=7, fill="#EFEAE4", outline=None)
        filled = chart_left + int(((chart_right - chart_left) * value / max_value) if max_value else 0)
        draw.rounded_rectangle((chart_left, y + 4, filled, y + 20), radius=7, fill=color, outline=None)
        draw.text((filled + 10, y), str(value), font=TINY_FONT, fill=PALETTE["ink"])


def export_image(image: Image.Image, stem: str) -> dict[str, str]:
    png_path = FIGURE_DIR / f"{stem}.png"
    pdf_path = FIGURE_DIR / f"{stem}.pdf"
    image.save(png_path, format="PNG")
    image.save(pdf_path, format="PDF", resolution=200.0)
    return {"png": str(png_path), "pdf": str(pdf_path)}


def generate_system_overview() -> dict:
    image, draw = new_canvas(1800, 820)
    draw.text((70, 48), "homekgmas System Overview", font=TITLE_FONT, fill=PALETTE["ink"])
    draw.text(
        (70, 108),
        "A local-first smart-home multi-agent loop spanning perception, discussion, coordination, execution, and memory.",
        font=SUBTITLE_FONT,
        fill=PALETTE["muted"],
    )

    draw_panel(draw, (80, 220, 420, 390), "Task Input", "User request or scheduled task", PALETTE["panel"])
    draw_panel(draw, (80, 470, 420, 640), "Home Context", "Dynamic simulator sensors, outdoor state, and device state", PALETTE["panel"])
    draw_panel(draw, (560, 330, 980, 560), "CentralNode", "Topic building, agent wakeup, discussion, consensus, execution, and memory persistence", PALETTE["panel_alt"])
    draw_panel(draw, (1120, 170, 1450, 315), "CoolingAgent", "Thermal comfort and energy trade-off reasoning", PALETTE["panel"])
    draw_panel(draw, (1120, 360, 1450, 505), "LightingAgent", "Ambient scene and brightness coordination", PALETTE["panel"])
    draw_panel(draw, (1120, 550, 1450, 695), "MusicAgent", "Playback selection with quiet-hours awareness", PALETTE["panel"])
    draw_panel(draw, (1510, 220, 1730, 410), "Local Memory", "JSON records, triples, short-term notes, and long-term workspace patterns", PALETTE["panel_alt"])
    draw_panel(draw, (1510, 480, 1730, 670), "Execution", "Coordinated device actions applied to the simulator backend", PALETTE["panel_alt"])

    draw_arrow(draw, (420, 305), (560, 390))
    draw_arrow(draw, (420, 555), (560, 500))
    draw_arrow(draw, (980, 405), (1120, 240))
    draw_arrow(draw, (980, 445), (1120, 430))
    draw_arrow(draw, (980, 485), (1120, 620))
    draw_arrow(draw, (1450, 240), (1510, 315))
    draw_arrow(draw, (1450, 430), (1510, 315))
    draw_arrow(draw, (1450, 620), (1510, 575))
    draw_arrow(draw, (1510, 575), (980, 540))

    exports = export_image(image, "system_overview")
    return {
        "id": "system_overview",
        "title": "System Overview",
        "surface_class": "paper_main",
        "source_data": [
            "app/orchestrator/central_node.py",
            "app/orchestrator/discussion_manager.py",
            "app/memory/coordinator.py",
            "app/environment/simulator.py",
        ],
        "exports": exports,
        "claim": "The system forms a complete local-first coordination loop from task input to memory persistence.",
        "review_note": "Kept the architecture left-to-right and reduced component text so the full loop remains readable on a slide.",
    }


def generate_benchmark_snapshot() -> dict:
    report_path = PROJECT_ROOT / "outputs" / "reports" / "benchmark_report.json"
    report = read_json(report_path)
    records = report.get("records", [])
    labels = [f"T{i + 1}" for i in range(len(records))]
    mas_actions = [row["mas_action_count"] for row in records]
    baseline_actions = [row["baseline_action_count"] for row in records]
    conflicts = [row["mas_conflict_count"] for row in records]
    summary = report.get("summary", {})

    image, draw = new_canvas(1800, 820)
    draw.text((70, 48), "Initial Benchmark Snapshot", font=TITLE_FONT, fill=PALETTE["ink"])
    draw.text(
        (70, 108),
        "A compact comparison between the current multi-agent system and the simple keyword baseline.",
        font=SUBTITLE_FONT,
        fill=PALETTE["muted"],
    )

    draw_grouped_bar_chart(
        draw,
        (70, 190, 1080, 690),
        labels,
        [mas_actions, baseline_actions],
        ["MAS", "Keyword baseline"],
        [PALETTE["sage"], PALETTE["clay"]],
        "Per-task selected action count",
    )
    draw_vertical_chart(
        draw,
        (1140, 190, 1720, 520),
        labels,
        conflicts,
        [PALETTE["rose"]] * max(len(labels), 1),
        "Conflict count",
    )
    draw_panel(
        draw,
        (1140, 550, 1720, 700),
        "Summary",
        (
            f"Tasks: {summary.get('task_count', 0)}\n"
            f"MAS avg actions: {summary.get('mas_avg_action_count', 0):.2f}\n"
            f"Baseline avg actions: {summary.get('baseline_avg_action_count', 0):.2f}\n"
            f"MAS success rate: {summary.get('mas_success_rate', 0):.2f}"
        ),
        PALETTE["panel"],
    )
    draw.text(
        (70, 745),
        "T1-T3 correspond to the benchmark tasks recorded in outputs/reports/benchmark_report.json.",
        font=SMALL_FONT,
        fill=PALETTE["muted"],
    )

    exports = export_image(image, "benchmark_snapshot")
    return {
        "id": "benchmark_snapshot",
        "title": "Initial Benchmark Snapshot",
        "surface_class": "paper_main",
        "source_data": [str(report_path.relative_to(PROJECT_ROOT))],
        "exports": exports,
        "claim": "The current repository already contains a small but presentation-ready benchmark comparison against a baseline.",
        "review_note": "Separated action counts and conflict counts so the slide carries one compact experimental message without overcrowding.",
    }


def generate_knowledge_graph_summary() -> dict:
    report_path = PROJECT_ROOT / "outputs" / "reports" / "knowledge_graph_report.json"
    report = read_json(report_path)
    summary = report.get("summary", {})
    predicates = summary.get("predicate_breakdown", {})
    top_agents = summary.get("top_agents", [])
    top_actions = summary.get("top_actions", [])[:6]

    image, draw = new_canvas(1900, 860)
    draw.text((70, 48), "Local Memory Graph Summary", font=TITLE_FONT, fill=PALETTE["ink"])
    draw.text(
        (70, 108),
        f"Tasks: {summary.get('task_count', 0)}   Nodes: {summary.get('node_count', 0)}   Edges: {summary.get('edge_count', 0)}",
        font=SUBTITLE_FONT,
        fill=PALETTE["muted"],
    )

    draw_vertical_chart(
        draw,
        (70, 200, 620, 730),
        list(predicates.keys()),
        list(predicates.values()),
        [PALETTE["sage"], PALETTE["clay"], PALETTE["ink"], PALETTE["rose"]],
        "Predicate breakdown",
    )

    agent_labels = [item[0].replace("_agent", "") for item in top_agents]
    agent_counts = [item[1] for item in top_agents]
    draw_horizontal_bars(
        draw,
        (690, 200, 1190, 730),
        agent_labels,
        agent_counts,
        PALETTE["sage"],
        "Most frequent agents",
    )

    action_labels = [item[0].replace("living_room_", "LR ") for item in top_actions]
    action_counts = [item[1] for item in top_actions]
    draw_horizontal_bars(
        draw,
        (1260, 200, 1820, 730),
        action_labels,
        action_counts,
        PALETTE["clay"],
        "Most frequent final actions",
    )

    exports = export_image(image, "knowledge_graph_summary")
    return {
        "id": "knowledge_graph_summary",
        "title": "Local Memory Graph Summary",
        "surface_class": "paper_main",
        "source_data": [
            str(report_path.relative_to(PROJECT_ROOT)),
            "outputs/reports/knowledge_graph_report.mmd",
        ],
        "exports": exports,
        "claim": "The stored execution history already supports graph-style analysis over tasks, agents, actions, and conflicts.",
        "review_note": "Used summary statistics instead of the full Mermaid graph because the condensed view reads more clearly in presentation mode.",
    }


def generate_dual_memory_organization() -> dict:
    workspace_root = PROJECT_ROOT / "outputs" / "agent_workspaces" / "fusion"
    memory_root = PROJECT_ROOT / "outputs" / "memory"
    agent_names = ["cooling_agent", "lighting_agent", "music_agent"]
    short_counts = []
    long_counts = []
    for agent in agent_names:
        short_counts.append(len(read_jsonl(workspace_root / agent / "memory" / "short_term.jsonl")))
        long_counts.append(len(read_jsonl(workspace_root / agent / "memory" / "long_term.jsonl")))

    record_count = len(list((memory_root / "records").glob("*.json")))
    triple_count = len(read_jsonl(memory_root / "triples.jsonl"))

    image, draw = new_canvas(1800, 820)
    draw.text((70, 48), "Dual Memory Organization", font=TITLE_FONT, fill=PALETTE["ink"])
    draw.text(
        (70, 108),
        "The repository maintains both graph-like task memory and agent-local workspace memory.",
        font=SUBTITLE_FONT,
        fill=PALETTE["muted"],
    )

    draw_grouped_bar_chart(
        draw,
        (70, 200, 970, 690),
        [name.replace("_agent", "") for name in agent_names],
        [short_counts, long_counts],
        ["Short-term", "Long-term"],
        [PALETTE["sage"], PALETTE["clay"]],
        "Workspace entry count by agent",
    )
    draw_panel(
        draw,
        (1070, 220, 1710, 390),
        "Triple / Graph Memory",
        f"Task records: {record_count}\nTriples: {triple_count}\nUsed for graph-like retrieval and global task history.",
        PALETTE["panel"],
    )
    draw_panel(
        draw,
        (1070, 470, 1710, 640),
        "Workspace Memory",
        "Short-term notes preserve recent episodes. Long-term notes preserve durable patterns per agent.",
        PALETTE["panel_alt"],
    )
    draw_arrow(draw, (1390, 390), (1390, 470))
    draw.text(
        (1080, 680),
        "Both memory paths are kept in parallel so retrieval backends can be swapped at runtime.",
        font=SMALL_FONT,
        fill=PALETTE["muted"],
    )

    exports = export_image(image, "dual_memory_organization")
    return {
        "id": "dual_memory_organization",
        "title": "Dual Memory Organization",
        "surface_class": "paper_main",
        "source_data": [
            "outputs/agent_workspaces/fusion/*/memory/*.jsonl",
            "outputs/memory/records/*.json",
            "outputs/memory/triples.jsonl",
        ],
        "exports": exports,
        "claim": "The system already exposes a concrete dual-memory design suitable for explaining backend modularity and agent-specific persistence.",
        "review_note": "Combined real entry counts with a simplified pathway diagram to keep the figure concrete and presentation-friendly.",
    }


def generate_case_study() -> dict:
    record_path = PROJECT_ROOT / "outputs" / "memory" / "records" / "task-be567f68-it-s-morning-please-make.json"
    record = read_json(record_path)
    proposals = record.get("proposals", [])
    proposal_summary = []
    for proposal in proposals:
        short_name = proposal["agent_name"].replace("_agent", "")
        proposal_summary.append(f"{short_name}: {len(proposal.get('actions', []))} action(s)")
    actions = record.get("final_actions", [])
    action_lines = [
        f"{action['device_id']}.{action['attribute']} = {action['value']}"
        for action in actions[:6]
    ]

    image, draw = new_canvas(1800, 820)
    draw.text((70, 48), "Case Study: End-to-End Orchestration Record", font=TITLE_FONT, fill=PALETTE["ink"])
    draw.text((70, 108), f"Record ID: {record.get('record_id', '')}", font=SUBTITLE_FONT, fill=PALETTE["muted"])

    draw_panel(draw, (80, 210, 490, 430), "Task", record["task_summary"], PALETTE["panel"])
    draw_panel(
        draw,
        (690, 210, 1110, 430),
        "Discussion",
        "\n".join(proposal_summary) if proposal_summary else "No proposals stored.",
        PALETTE["panel_alt"],
    )
    draw_panel(
        draw,
        (1310, 210, 1710, 430),
        "Outcome",
        (
            f"Rounds completed: {record.get('rounds_completed', 0)}\n"
            f"Conflict count: {len(record.get('conflicts', []))}\n"
            f"Execution success: {record.get('outcome', {}).get('success', False)}"
        ),
        PALETTE["panel"],
    )
    draw_panel(
        draw,
        (220, 520, 1580, 700),
        "Final coordinated actions",
        "\n".join(action_lines) if action_lines else "No device changes were executed for this case.",
        PALETTE["panel_alt"],
    )
    draw_arrow(draw, (490, 320), (690, 320))
    draw_arrow(draw, (1110, 320), (1310, 320))
    draw_arrow(draw, (900, 430), (900, 520))

    exports = export_image(image, "case_study_end_to_end")
    return {
        "id": "case_study_end_to_end",
        "title": "Case Study: End-to-End Orchestration Record",
        "surface_class": "paper_main",
        "source_data": [str(record_path.relative_to(PROJECT_ROOT))],
        "exports": exports,
        "claim": "A single stored memory record is enough to present the full task-to-outcome loop as a qualitative case study.",
        "review_note": "Converted dense JSON into a four-block slide layout to make the orchestration trajectory understandable in seconds.",
    }


def main() -> None:
    ensure_dirs()
    catalog = [
        generate_system_overview(),
        generate_benchmark_snapshot(),
        generate_knowledge_graph_summary(),
        generate_dual_memory_organization(),
        generate_case_study(),
    ]
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps({"figure_dir": str(FIGURE_DIR), "figure_count": len(catalog)}, indent=2))


if __name__ == "__main__":
    main()
