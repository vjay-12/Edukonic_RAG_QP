import json
from pathlib import Path
from typing import List, Dict, Any
from fastapi import APIRouter

router = APIRouter(prefix="/blueprints", tags=["Blueprints"])

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs"

@router.get("", response_model=List[Dict[str, Any]])
def list_blueprints():
    """Retrieve available paper configuration presets (e.g. 25-mark unit test, 80-mark board exam)."""
    presets = []
    if CONFIGS_DIR.exists():
        for file in sorted(CONFIGS_DIR.glob("*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["preset_id"] = file.stem
                    presets.append(data)
            except Exception:
                continue
    return presets
