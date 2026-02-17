"""Analysis module for council deliberation.

Provides ranking conflict detection and minority opinion detection
to surface meaningful disagreements during deliberation.
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict


def detect_ranking_conflicts(
    rankings: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Detect conflicts in model rankings.
    
    Looks for:
    1. Mutual opposition: Two models rank each other low
    2. Ranking swaps: Large position differences for same response across rankers
    
    Args:
        rankings: List of ranking results from Stage 2, each with 'model' and 'parsed_ranking'
        label_to_model: Mapping from response labels to model IDs
    
    Returns:
        List of conflict dicts with 'type', 'description', 'severity', 'models'
    """
    conflicts = []
    
    if len(rankings) < 2:
        return conflicts
    
    # Build position maps: for each ranker, what position did each response get?
    position_maps = {}  # ranker_model -> {response_label: position}
    for ranking in rankings:
        ranker = ranking.get("model", "unknown")
        parsed = ranking.get("parsed_ranking", [])
        if not parsed:
            continue
        pos_map = {}
        for i, entry in enumerate(parsed):
            label = entry if isinstance(entry, str) else entry.get("label", entry.get("response", ""))
            pos_map[label] = i + 1
        position_maps[ranker] = pos_map
    
    # Detect ranking swaps (large position differences)
    response_labels = set()
    for pm in position_maps.values():
        response_labels.update(pm.keys())
    
    for label in response_labels:
        positions = []
        for ranker, pm in position_maps.items():
            if label in pm:
                positions.append((ranker, pm[label]))
        
        if len(positions) < 2:
            continue
        
        # Check for large disagreements
        min_pos = min(p for _, p in positions)
        max_pos = max(p for _, p in positions)
        spread = max_pos - min_pos
        
        if spread >= 3:  # Significant disagreement (e.g., ranked #1 by one, #4+ by another)
            high_rankers = [r for r, p in positions if p == min_pos]
            low_rankers = [r for r, p in positions if p == max_pos]
            conflicts.append({
                "type": "ranking_swap",
                "response": label,
                "description": f"{label} ranked #{min_pos} by {high_rankers[0]} but #{max_pos} by {low_rankers[0]}",
                "severity": "high" if spread >= 4 else "medium",
                "spread": spread,
                "models": {"high": high_rankers, "low": low_rankers},
            })
        elif spread >= 2:
            high_rankers = [r for r, p in positions if p == min_pos]
            low_rankers = [r for r, p in positions if p == max_pos]
            conflicts.append({
                "type": "ranking_swap",
                "response": label,
                "description": f"{label} has position spread of {spread} (#{min_pos} to #{max_pos})",
                "severity": "low",
                "spread": spread,
                "models": {"high": high_rankers, "low": low_rankers},
            })
    
    # Detect mutual opposition
    model_to_label = {v: k for k, v in label_to_model.items()}
    ranker_models = list(position_maps.keys())
    
    for i, ranker_a in enumerate(ranker_models):
        for ranker_b in ranker_models[i+1:]:
            label_a = model_to_label.get(ranker_a)
            label_b = model_to_label.get(ranker_b)
            
            if not label_a or not label_b:
                continue
            
            pm_a = position_maps.get(ranker_a, {})
            pm_b = position_maps.get(ranker_b, {})
            
            # Does A rank B's response low AND B rank A's response low?
            pos_of_b_by_a = pm_a.get(label_b)
            pos_of_a_by_b = pm_b.get(label_a)
            
            num_responses = max(len(pm_a), len(pm_b))
            if num_responses < 3:
                continue
            
            threshold = max(3, num_responses - 1)  # Bottom positions
            
            if pos_of_b_by_a and pos_of_a_by_b:
                if pos_of_b_by_a >= threshold and pos_of_a_by_b >= threshold:
                    conflicts.append({
                        "type": "mutual_opposition",
                        "description": f"{ranker_a} and {ranker_b} rank each other's responses low",
                        "severity": "high",
                        "models": [ranker_a, ranker_b],
                        "details": {
                            f"{ranker_a}_ranked_{label_b}": pos_of_b_by_a,
                            f"{ranker_b}_ranked_{label_a}": pos_of_a_by_b,
                        },
                    })
    
    return conflicts


def detect_minority_opinions(
    rankings: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
    threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Detect well-reasoned minority opinions (dissent from consensus).
    
    A minority opinion exists when >= threshold of rankers disagree with
    the consensus ranking for a response.
    
    Args:
        rankings: Ranking results from Stage 2
        label_to_model: Response label to model mapping
        threshold: Fraction of rankers who must disagree (default 0.3 = 30%)
    
    Returns:
        List of minority opinion dicts with 'response', 'consensus_position',
        'dissenting_models', 'dissent_direction', 'reasoning'
    """
    minority_opinions = []
    
    if len(rankings) < 3:
        return minority_opinions
    
    # Calculate consensus (average) position for each response
    position_counts = defaultdict(list)
    for ranking in rankings:
        parsed = ranking.get("parsed_ranking", [])
        for i, entry in enumerate(parsed):
            label = entry if isinstance(entry, str) else entry.get("label", entry.get("response", ""))
            position_counts[label].append(i + 1)
    
    num_rankers = len(rankings)
    min_dissenters = max(1, int(num_rankers * threshold))
    
    for label, positions in position_counts.items():
        if len(positions) < 2:
            continue
        
        avg_position = sum(positions) / len(positions)
        
        # Find dissenters: models who rank this significantly different from consensus
        dissenters_high = []  # Think it should be ranked higher
        dissenters_low = []   # Think it should be ranked lower
        
        for ranking, pos in zip(rankings, positions):
            diff = pos - avg_position
            if diff >= 1.5:  # Ranked much lower than consensus
                dissenters_low.append({
                    "model": ranking.get("model", "unknown"),
                    "position": pos,
                    "consensus": round(avg_position, 1),
                })
            elif diff <= -1.5:  # Ranked much higher than consensus
                dissenters_high.append({
                    "model": ranking.get("model", "unknown"),
                    "position": pos,
                    "consensus": round(avg_position, 1),
                })
        
        if len(dissenters_high) >= min_dissenters:
            minority_opinions.append({
                "response": label,
                "model": label_to_model.get(label, "unknown"),
                "consensus_position": round(avg_position, 1),
                "dissent_direction": "higher",
                "dissenting_models": [d["model"] for d in dissenters_high],
                "details": dissenters_high,
                "description": f"{len(dissenters_high)}/{num_rankers} rankers think {label} deserves higher ranking (consensus: #{round(avg_position, 1)})",
            })
        
        if len(dissenters_low) >= min_dissenters:
            minority_opinions.append({
                "response": label,
                "model": label_to_model.get(label, "unknown"),
                "consensus_position": round(avg_position, 1),
                "dissent_direction": "lower",
                "dissenting_models": [d["model"] for d in dissenters_low],
                "details": dissenters_low,
                "description": f"{len(dissenters_low)}/{num_rankers} rankers think {label} is overrated (consensus: #{round(avg_position, 1)})",
            })
    
    return minority_opinions


def calculate_weighted_rankings(
    rankings: List[Dict[str, Any]],
    rubric_scores: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """
    Calculate weighted aggregate rankings from individual model rankings.
    
    Uses position-based scoring: 1st place gets N points, 2nd gets N-1, etc.
    Optionally incorporates rubric scores for weighted voting.
    
    Args:
        rankings: List of ranking results
        rubric_scores: Optional per-criterion scores from rubric-based evaluation
    
    Returns:
        Dict mapping response labels to aggregate scores (higher = better)
    """
    scores = defaultdict(float)
    
    for ranking in rankings:
        parsed = ranking.get("parsed_ranking", [])
        num_responses = len(parsed)
        
        for i, entry in enumerate(parsed):
            label = entry if isinstance(entry, str) else entry.get("label", entry.get("response", ""))
            # Borda count: first place gets num_responses points, last gets 1
            scores[label] += num_responses - i
    
    # Incorporate rubric scores if available
    if rubric_scores:
        for score_entry in rubric_scores:
            label = score_entry.get("response", "")
            weighted_score = score_entry.get("weighted_score", 0)
            if label and weighted_score:
                scores[label] += weighted_score * 0.5  # Blend with ranking scores
    
    return dict(scores)


def get_top_response(
    weighted_scores: Dict[str, float],
    label_to_model: Dict[str, str],
) -> Tuple[str, str, float]:
    """
    Get the top-voted response label, model, and score.
    
    Returns:
        Tuple of (response_label, model_id, score)
    """
    if not weighted_scores:
        return ("", "", 0.0)
    
    top_label = max(weighted_scores, key=weighted_scores.get)
    return (top_label, label_to_model.get(top_label, "unknown"), weighted_scores[top_label])


def format_analysis_summary(
    conflicts: List[Dict[str, Any]],
    minority_opinions: List[Dict[str, Any]],
    weighted_scores: Dict[str, float],
) -> str:
    """Format analysis results as a summary string for inclusion in prompts."""
    parts = []
    
    if weighted_scores:
        sorted_scores = sorted(weighted_scores.items(), key=lambda x: x[1], reverse=True)
        parts.append("WEIGHTED RANKINGS:")
        for i, (label, score) in enumerate(sorted_scores, 1):
            parts.append(f"  {i}. {label}: {score:.1f} points")
    
    if conflicts:
        parts.append("\nCONFLICTS DETECTED:")
        for c in conflicts:
            parts.append(f"  [{c['severity'].upper()}] {c['description']}")
    
    if minority_opinions:
        parts.append("\nMINORITY OPINIONS:")
        for mo in minority_opinions:
            parts.append(f"  {mo['description']}")
    
    return "\n".join(parts)
