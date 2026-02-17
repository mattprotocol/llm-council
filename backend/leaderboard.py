"""Leaderboard tracking for per-model performance per council."""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
LEADERBOARD_FILE = DATA_DIR / "leaderboard.json"


def _load_leaderboard() -> Dict[str, Any]:
    """Load leaderboard data from file."""
    if LEADERBOARD_FILE.exists():
        try:
            with open(LEADERBOARD_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"councils": {}, "last_updated": None}


def _save_leaderboard(data: Dict[str, Any]):
    """Save leaderboard data to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _ensure_model_entry(council_data: Dict, model_id: str) -> Dict:
    """Ensure a model entry exists in council data."""
    if model_id not in council_data:
        council_data[model_id] = {
            "wins": 0,
            "participations": 0,
            "total_score": 0.0,
            "avg_position": 0.0,
            "positions": [],  # Last 50 positions
            "rubric_scores": {},  # criterion_name -> [scores]
        }
    return council_data[model_id]


def record_deliberation_result(
    council_id: str,
    model_scores: Dict[str, float],
    winner_model: str,
    rubric_scores: Optional[Dict[str, Dict[str, float]]] = None,
):
    """
    Record the result of a council deliberation.
    
    Args:
        council_id: Which council (protocol, personal, downeast)
        model_scores: Dict mapping model_id to aggregate score
        winner_model: Model ID of the winning response
        rubric_scores: Optional dict of model_id -> {criterion: score}
    """
    data = _load_leaderboard()
    
    if council_id not in data["councils"]:
        data["councils"][council_id] = {}
    
    council = data["councils"][council_id]
    
    # Sort models by score to get positions
    sorted_models = sorted(model_scores.items(), key=lambda x: x[1], reverse=True)
    
    for position, (model_id, score) in enumerate(sorted_models, 1):
        entry = _ensure_model_entry(council, model_id)
        entry["participations"] += 1
        entry["total_score"] += score
        entry["positions"].append(position)
        
        # Keep only last 50 positions
        if len(entry["positions"]) > 50:
            entry["positions"] = entry["positions"][-50:]
        
        entry["avg_position"] = sum(entry["positions"]) / len(entry["positions"])
        
        if model_id == winner_model:
            entry["wins"] += 1
        
        # Record rubric scores if available
        if rubric_scores and model_id in rubric_scores:
            for criterion, criterion_score in rubric_scores[model_id].items():
                if criterion not in entry["rubric_scores"]:
                    entry["rubric_scores"][criterion] = []
                entry["rubric_scores"][criterion].append(criterion_score)
                # Keep last 50
                if len(entry["rubric_scores"][criterion]) > 50:
                    entry["rubric_scores"][criterion] = entry["rubric_scores"][criterion][-50:]
    
    _save_leaderboard(data)


def get_council_leaderboard(council_id: str) -> List[Dict[str, Any]]:
    """
    Get leaderboard for a specific council.
    
    Returns:
        List of model performance dicts sorted by win rate
    """
    data = _load_leaderboard()
    council = data.get("councils", {}).get(council_id, {})
    
    leaderboard = []
    for model_id, entry in council.items():
        win_rate = (entry["wins"] / entry["participations"] * 100) if entry["participations"] > 0 else 0
        avg_score = entry["total_score"] / entry["participations"] if entry["participations"] > 0 else 0
        
        # Calculate average rubric scores
        avg_rubric = {}
        for criterion, scores in entry.get("rubric_scores", {}).items():
            avg_rubric[criterion] = sum(scores) / len(scores) if scores else 0
        
        leaderboard.append({
            "model": model_id,
            "wins": entry["wins"],
            "participations": entry["participations"],
            "win_rate": round(win_rate, 1),
            "avg_score": round(avg_score, 2),
            "avg_position": round(entry["avg_position"], 2),
            "rubric_scores": avg_rubric,
        })
    
    leaderboard.sort(key=lambda x: x["win_rate"], reverse=True)
    return leaderboard


def get_all_leaderboards() -> Dict[str, List[Dict[str, Any]]]:
    """Get leaderboards for all councils."""
    data = _load_leaderboard()
    result = {}
    for council_id in data.get("councils", {}).keys():
        result[council_id] = get_council_leaderboard(council_id)
    return result
