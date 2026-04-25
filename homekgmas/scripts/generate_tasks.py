from pathlib import Path
import sys
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datasets.loaders.task_builder import build_demo_tasks


if __name__ == "__main__":
    tasks = [task.model_dump(mode="json") for task in build_demo_tasks()]
    print(json.dumps(tasks, indent=2))
