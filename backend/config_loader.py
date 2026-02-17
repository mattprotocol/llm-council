"""YAML-based configuration loader for multi-council LLM Council."""

import os
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

_config_cache: Optional[Dict[str, Any]] = None
_councils_cache: Optional[Dict[str, Dict[str, Any]]] = None


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def _load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> Dict[str, Any]:
    """Load global model configuration from config/models.yaml."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = get_project_root() / "config" / "models.yaml"
    if config_path.exists():
        _config_cache = _load_yaml(config_path)
        print(f"Loaded configuration from {config_path}")
    else:
        print(f"Warning: {config_path} not found, using defaults")
        _config_cache = {
            "models": [
                {"id": "anthropic/claude-opus-4", "name": "Claude Opus 4"},
                {"id": "openai/gpt-5.1", "name": "GPT-5.1"},
                {"id": "google/gemini-3-pro-preview", "name": "Gemini 3 Pro"},
            ],
            "chairman": "anthropic/claude-opus-4",
            "title_model": "google/gemini-2.5-flash",
            "deliberation": {"rounds": 2, "max_rounds": 5},
            "response_config": {"response_style": "standard"},
            "timeout_config": {
                "default_timeout": 120,
                "streaming_chunk_timeout": 120,
                "connection_timeout": 30,
                "max_retries": 1,
                "retry_backoff_factor": 2,
            },
        }
    return _config_cache


def reload_config():
    """Force reload configuration from disk."""
    global _config_cache, _councils_cache
    _config_cache = None
    _councils_cache = None
    return load_config()


def load_councils() -> Dict[str, Dict[str, Any]]:
    """Load all council configurations from config/councils/*.yaml."""
    global _councils_cache
    if _councils_cache is not None:
        return _councils_cache

    councils_dir = get_project_root() / "config" / "councils"
    _councils_cache = {}

    if not councils_dir.exists():
        print(f"Warning: {councils_dir} not found")
        return _councils_cache

    for yaml_file in sorted(councils_dir.glob("*.yaml")):
        council_id = yaml_file.stem  # filename without .yaml
        try:
            council_data = _load_yaml(yaml_file)
            council_data["id"] = council_id
            _councils_cache[council_id] = council_data
            print(f"Loaded council: {council_data.get('name', council_id)} ({council_id})")
        except Exception as e:
            print(f"Error loading council {yaml_file}: {e}")

    return _councils_cache


def get_council(council_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific council configuration."""
    councils = load_councils()
    return councils.get(council_id)


def get_council_ids() -> List[str]:
    """Get list of available council IDs."""
    return list(load_councils().keys())


def get_council_models() -> List[str]:
    """Get list of council model IDs from global config."""
    config = load_config()
    return [m["id"] for m in config.get("models", [])]


def get_chairman_model() -> str:
    """Get chairman model ID."""
    config = load_config()
    return config.get("chairman", "anthropic/claude-opus-4")


def get_title_model() -> str:
    """Get title generation model ID (cheap/fast)."""
    config = load_config()
    return config.get("title_model", "google/gemini-2.5-flash")


def get_deliberation_config() -> Dict[str, Any]:
    config = load_config()
    return config.get("deliberation", {"rounds": 2, "max_rounds": 5})


def get_deliberation_rounds() -> int:
    return get_deliberation_config().get("rounds", 2)


def get_response_config() -> Dict[str, Any]:
    config = load_config()
    return config.get("response_config", {"response_style": "standard"})


def get_timeout_config() -> Dict[str, Any]:
    config = load_config()
    return config.get("timeout_config", {
        "default_timeout": 120,
        "streaming_chunk_timeout": 120,
        "connection_timeout": 30,
        "max_retries": 1,
        "retry_backoff_factor": 2,
    })


def get_persona_for_model(council_id: str, model_id: str) -> Optional[Dict[str, Any]]:
    """Get the persona config for a specific model in a specific council."""
    council = get_council(council_id)
    if not council:
        return None
    for persona in council.get("personas", []):
        if persona.get("model") == model_id:
            return persona
    return None


def get_rubric(council_id: str) -> List[Dict[str, Any]]:
    """Get the rubric criteria for a council."""
    council = get_council(council_id)
    if not council:
        return []
    return council.get("rubric", [])


def get_councils_summary() -> List[Dict[str, Any]]:
    """Get summary of all councils for API response."""
    councils = load_councils()
    return [
        {
            "id": cid,
            "name": c.get("name", cid),
            "description": c.get("description", ""),
            "personas": [
                {"model": p.get("model"), "role": p.get("role")}
                for p in c.get("personas", [])
            ],
            "rubric": c.get("rubric", []),
        }
        for cid, c in councils.items()
    ]
