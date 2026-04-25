from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

SERVER_DIR = Path(__file__).resolve().parent
STATIC_DIR = SERVER_DIR.parent / "screen-display"
LAYOUT_PATH = STATIC_DIR / "layout.json"
BACKUP_DIR = STATIC_DIR / ".layout_backups"
MAX_BACKUPS = 10
LAYOUT_VERSION = 1


class LayoutPayload(BaseModel):
    transforms: Dict[str, Any]


app = FastAPI(title="Screen-Display Layout Saver")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "layoutPath": str(LAYOUT_PATH),
        "exists": LAYOUT_PATH.exists(),
    }


@app.get("/api/layout")
def get_layout() -> Dict[str, Any]:
    if not LAYOUT_PATH.exists():
        return {"version": LAYOUT_VERSION, "updatedAt": None, "transforms": {}}
    try:
        with LAYOUT_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read layout: {exc}")


@app.post("/api/save-layout")
def save_layout(payload: LayoutPayload) -> Dict[str, Any]:
    if LAYOUT_PATH.exists():
        BACKUP_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"layout.{timestamp}.json"
        shutil.copy2(LAYOUT_PATH, backup)
        existing = sorted(BACKUP_DIR.glob("layout.*.json"))
        for old in existing[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass

    data: Dict[str, Any] = {
        "version": LAYOUT_VERSION,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "transforms": payload.transforms,
    }
    with LAYOUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return {
        "ok": True,
        "saved": str(LAYOUT_PATH),
        "count": len(payload.transforms),
        "updatedAt": data["updatedAt"],
    }
