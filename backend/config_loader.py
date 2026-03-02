"""YAML-based configuration loader for multi-council LLM Council."""

import os
import yaml
from dataclasses import dataclass
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


def save_models_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Save global model configuration to config/models.yaml."""
    config_path = get_project_root() / "config" / "models.yaml"
    current = load_config().copy()
    current.update(data)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(current, f, default_flow_style=False, allow_unicode=True)
    reload_config()
    return current


def save_council_config(council_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Save a council configuration to config/councils/{council_id}.yaml."""
    councils_dir = get_project_root() / "config" / "councils"
    councils_dir.mkdir(parents=True, exist_ok=True)
    config_path = councils_dir / f"{council_id}.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    global _councils_cache
    _councils_cache = None
    return data


def delete_council_config(council_id: str) -> None:
    """Delete a council configuration file."""
    config_path = get_project_root() / "config" / "councils" / f"{council_id}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Council config not found: {council_id}")
    if council_id in ("personal",):
        raise ValueError(f"Cannot delete built-in council: {council_id}")
    config_path.unlink()
    global _councils_cache
    _councils_cache = None


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


def get_stage_temperatures() -> Dict[str, float]:
    """Get per-stage temperature settings."""
    config = get_deliberation_config()
    temps = config.get("temperatures", {})
    return {
        "stage1": temps.get("stage1", 0.5),
        "stage2": temps.get("stage2", 0.3),
        "stage3": temps.get("stage3", 0.4),
    }


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


# ============== Council Member & Advisor Functions ==============

@dataclass
class CouncilMember:
    """A council member with model, role, system prompt, and unique ID."""
    model: str
    role: str
    system_prompt: str
    member_id: str


def _persona_to_advisor(persona: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Convert a persona config entry to an advisor dict."""
    role = persona.get("role", f"Member {index + 1}")
    model = persona.get("model", "")
    member_id = role.lower().replace(" ", "-").replace("'", "")
    return {
        "id": member_id,
        "name": role,
        "role": role,
        "model": model,
        "prompt": persona.get("prompt", ""),
        "tags": persona.get("tags", []),
    }


def get_advisors(council_id: str) -> List[Dict[str, Any]]:
    """Get full advisor list for a council (derived from personas)."""
    council = get_council(council_id)
    if not council:
        return []
    return [
        _persona_to_advisor(p, i)
        for i, p in enumerate(council.get("personas", []))
    ]


def get_advisor_roster_summary(council_id: str) -> List[Dict[str, Any]]:
    """Get a summary of advisors for routing (id, name, role, tags)."""
    advisors = get_advisors(council_id)
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "role": a["role"],
            "tags": a.get("tags", []),
        }
        for a in advisors
    ]


def get_routing_config(council_id: str) -> Dict[str, Any]:
    """Get routing configuration for a council."""
    council = get_council(council_id)
    if not council:
        return {"min_advisors": 3, "max_advisors": 5, "default_advisors": 5}
    routing = council.get("routing", {})
    num_personas = len(council.get("personas", []))
    return {
        "min_advisors": routing.get("min_advisors", min(3, num_personas)),
        "max_advisors": routing.get("max_advisors", num_personas),
        "default_advisors": routing.get("default_advisors", num_personas),
    }


def get_council_members(
    council_id: str,
    panel: Optional[List[Dict[str, str]]] = None,
) -> List[CouncilMember]:
    """Build CouncilMember list from council config.

    If panel is provided (from router), use those advisor_ids with their
    assigned models. Otherwise, use all personas from the council config.
    """
    council = get_council(council_id)
    if not council:
        return []

    personas = council.get("personas", [])
    advisors = get_advisors(council_id)
    advisor_map = {a["id"]: a for a in advisors}

    if panel:
        members = []
        for entry in panel:
            advisor_id = entry.get("advisor_id", "")
            model = entry.get("model", "")
            advisor = advisor_map.get(advisor_id)
            if advisor:
                members.append(CouncilMember(
                    model=model or advisor["model"],
                    role=advisor["role"],
                    system_prompt=advisor.get("prompt", ""),
                    member_id=advisor["id"],
                ))
        return members

    # No panel — use all personas
    return [
        CouncilMember(
            model=p.get("model", ""),
            role=p.get("role", f"Member {i + 1}"),
            system_prompt=p.get("prompt", ""),
            member_id=p.get("role", f"member-{i}").lower().replace(" ", "-").replace("'", ""),
        )
        for i, p in enumerate(personas)
    ]
