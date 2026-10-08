from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

_CONFIG_PATH = BASE_DIR / "config.yaml"

def load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_config()

DATA_DIR = BASE_DIR / CONFIG["paths"]["data_dir"]
CHROMA_DIR = BASE_DIR / CONFIG["paths"]["chroma_dir"]
DB_PATH = BASE_DIR / CONFIG["paths"]["sqlite_db"]
INGEST_DIR = BASE_DIR / CONFIG["paths"]["ingest_dir"]
PRIVATE_DIR = INGEST_DIR / "private"
PUBLIC_DIR = INGEST_DIR / "public"
COMPOSITION_DIR = INGEST_DIR / "composition"
TEMPLATES_DIR = BASE_DIR / CONFIG["paths"]["templates_dir"]

def _resolve_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else BASE_DIR / path

PPT_OUTPUT_DIR = _resolve_path(CONFIG["paths"]["ppt_output_dir"])

TEMPLATE_SLOTS = [1, 2, 3, 4, 5]

for _d in (DATA_DIR, CHROMA_DIR, INGEST_DIR, PRIVATE_DIR, PUBLIC_DIR, COMPOSITION_DIR, TEMPLATES_DIR, PPT_OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()

_HF_ENDPOINT = os.getenv("HF_ENDPOINT", "").strip()
if _HF_ENDPOINT:
    os.environ.setdefault("HF_ENDPOINT", _HF_ENDPOINT)

def api_key_ready() -> bool:
    return bool(DEEPSEEK_API_KEY) and "你的API key" not in DEEPSEEK_API_KEY and DEEPSEEK_API_KEY.startswith("sk-")

def authority_weight_map() -> dict[str, int]:
    return {item["name"]: int(item["weight"]) for item in CONFIG["tagging"]["authority"]}

def allowed_doc_types() -> list[str]:
    return CONFIG["tagging"]["doc_types"]

def allowed_grades() -> list[str]:
    return CONFIG["tagging"]["grades"]

def allowed_levels() -> list[str]:
    return ["A", "B", "C", "D", "E"]

def allowed_knowledge_points() -> list[str]:
    return CONFIG["tagging"]["knowledge_points"]

def allowed_learning_tags() -> list[str]:
    return CONFIG["tagging"]["learning_tags"]
