import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache
def load_tv_seed_rules() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "rules" / "tv_seed_rules.json"
    return json.loads(path.read_text(encoding="utf-8"))

