import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

TAXONOMY_PATH = Path(__file__).resolve().parent.parent.parent / "taxonomy.v1.json"

@lru_cache(maxsize=1)
def get_taxonomy() -> Dict[str, Any]:
    with open(TAXONOMY_PATH, "r") as f:
        data = json.load(f)
    return data

def allowed_values(facet: str) -> List[str]:
    taxonomy = get_taxonomy()
    return taxonomy["facets"][facet]["values"]
