from pathlib import Path
import sys
import json
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import build_settings
from app.memory.triple_store import TripleStore
from app.storage.file_store import FileStore


def _sanitize_node_id(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value)


if __name__ == "__main__":
    settings = build_settings()
    store = TripleStore(settings.memory_dir)
    file_store = FileStore()
    records = store.recent_records(limit=200)

    task_counter = 0
    predicate_counter = Counter()
    agent_counter = Counter()
    action_counter = Counter()
    conflict_counter = Counter()
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    neighbors = defaultdict(set)

    for record in records:
        task_counter += 1
        task_node = f"task:{record.task_id}"
        nodes[task_node] = {
            "id": task_node,
            "label": record.task_id,
            "type": "task",
            "task_summary": record.task_summary,
        }

        for triple in record.triples:
            predicate_counter[triple.predicate] += 1
            if triple.predicate == "involved_agent":
                agent_counter[triple.object] += 1
                object_node = f"agent:{triple.object}"
                nodes.setdefault(
                    object_node,
                    {"id": object_node, "label": triple.object, "type": "agent"},
                )
            elif triple.predicate == "final_action":
                action_counter[triple.object] += 1
                object_node = f"action:{triple.object}"
                nodes.setdefault(
                    object_node,
                    {"id": object_node, "label": triple.object, "type": "action"},
                )
            elif triple.predicate == "conflict":
                conflict_counter[triple.object] += 1
                object_node = f"conflict:{triple.object}"
                nodes.setdefault(
                    object_node,
                    {"id": object_node, "label": triple.object, "type": "conflict"},
                )
            else:
                object_node = f"value:{triple.object}"
                nodes.setdefault(
                    object_node,
                    {"id": object_node, "label": triple.object, "type": "value"},
                )

            edge = {
                "source": task_node,
                "target": object_node,
                "predicate": triple.predicate,
                "metadata": triple.metadata,
            }
            edges.append(edge)
            neighbors[task_node].add(object_node)
            neighbors[object_node].add(task_node)

    report = {
        "summary": {
            "task_count": task_counter,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "predicate_breakdown": dict(predicate_counter),
            "top_agents": agent_counter.most_common(10),
            "top_actions": action_counter.most_common(10),
            "top_conflicts": conflict_counter.most_common(10),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }

    report_path = settings.report_dir / "knowledge_graph_report.json"
    file_store.write_json(report_path, report)

    mermaid_lines = ["graph LR"]
    for edge in edges[:120]:
        source_id = _sanitize_node_id(edge["source"])
        target_id = _sanitize_node_id(edge["target"])
        source_label = nodes[edge["source"]]["label"]
        target_label = nodes[edge["target"]]["label"]
        mermaid_lines.append(f'    {source_id}["{source_label}"] -- "{edge["predicate"]}" --> {target_id}["{target_label}"]')
    mermaid_path = settings.report_dir / "knowledge_graph_report.mmd"
    file_store.write_text(mermaid_path, "\n".join(mermaid_lines) + "\n")

    print(json.dumps(report["summary"], indent=2, ensure_ascii=True))
    print(f"\nSaved graph report to: {report_path}")
    print(f"Saved Mermaid graph to: {mermaid_path}")
