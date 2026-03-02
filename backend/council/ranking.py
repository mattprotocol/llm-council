"""Ranking parsers and aggregate scoring for Stage 2 evaluation."""

import re
from typing import List, Dict, Any


def parse_ranking_from_text(text: str) -> List[str]:
    """Parse response labels from ranking text."""
    labels = []
    final_match = re.search(r"FINAL RANKING[:\s]*(.+)", text, re.DOTALL | re.IGNORECASE)
    search_text = final_match.group(1) if final_match else text

    pattern = r"(?:^|\n)\s*\d+\.\s*(?:Response\s+)?([A-Z])"
    matches = re.findall(pattern, search_text, re.IGNORECASE)
    for m in matches:
        label = f"Response {m.upper()}"
        if label not in labels:
            labels.append(label)
    return labels


def extract_quality_ratings(text: str) -> Dict[str, float]:
    ratings = {}
    pattern = r"(?:Response\s+)?([A-Z])\s*[:\(]\s*(\d+(?:\.\d+)?)\s*/\s*(?:5|10)"
    for match in re.finditer(pattern, text, re.IGNORECASE):
        label = f"Response {match.group(1).upper()}"
        score = float(match.group(2))
        if score > 5:
            score = score / 2
        ratings[label] = score
    return ratings


def extract_rubric_scores(text: str, rubric_criteria: List[str]) -> Dict[str, Dict[str, float]]:
    scores = {}
    for criterion in rubric_criteria:
        pattern = rf"{re.escape(criterion)}\s*[:\-]\s*(?:Response\s+)?([A-Z])\s*[:\(]\s*(\d+(?:\.\d+)?)"
        for match in re.finditer(pattern, text, re.IGNORECASE):
            label = f"Response {match.group(1).upper()}"
            score = float(match.group(2))
            if label not in scores:
                scores[label] = {}
            scores[label][criterion] = score
    return scores


def calculate_aggregate_rankings(rankings: List[Dict[str, Any]]) -> Dict[str, int]:
    scores = {}
    for ranking in rankings:
        parsed = ranking.get("parsed_ranking", [])
        for i, label in enumerate(parsed):
            if label not in scores:
                scores[label] = 0
            scores[label] += len(parsed) - i
    sorted_labels = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return {label: rank + 1 for rank, (label, _) in enumerate(sorted_labels)}
