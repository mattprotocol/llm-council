"""Stage 2: Multi-round peer rankings with rubric-based scoring."""

import asyncio
from typing import List, Dict, Any, Tuple, Optional, Callable

from ..openrouter import query_model_streaming
from ..config_loader import (
    get_deliberation_config, get_rubric, get_council_members, CouncilMember,
    get_stage_temperatures,
)
from ..analysis import (
    detect_ranking_conflicts, detect_minority_opinions,
    calculate_weighted_rankings, get_top_response,
)
from ..leaderboard import record_deliberation_result
from .utils import TokenTracker
from .ranking import parse_ranking_from_text, extract_quality_ratings, extract_rubric_scores


async def stage2_collect_rankings_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
    panel: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """Stage 2: Multi-round deliberation with rubric-based scoring."""
    deliberation_config = get_deliberation_config()
    max_rounds = deliberation_config.get("max_rounds", 3)
    temp = temperature if temperature is not None else get_stage_temperatures()["stage2"]
    rubric = get_rubric(council_id)
    members = get_council_members(council_id, panel=panel)

    labels = [chr(65 + i) for i in range(len(stage1_results))]

    label_to_model = {
        f"Response {label}": result["model"]
        for label, result in zip(labels, stage1_results)
    }

    label_to_member = {
        f"Response {label}": {
            "model": result["model"],
            "role": result.get("role", result["model"].split("/")[-1]),
            "member_id": result.get("member_id", result["model"].split("/")[-1]),
        }
        for label, result in zip(labels, stage1_results)
    }

    current_responses = {
        f"Response {label}": result["response"]
        for label, result in zip(labels, stage1_results)
    }

    all_rounds_rankings = []
    token_tracker = TokenTracker()

    # Emit init event with total count
    on_event("stage2_init", {"total": len(members)})

    for round_num in range(1, max_rounds + 1):
        on_event("round_start", {"round": round_num, "max_rounds": max_rounds})

        responses_text = "\n\n".join([
            f"{label}:\n{response}" for label, response in current_responses.items()
        ])

        rubric_text = ""
        if rubric:
            rubric_text = "\nScore each response on these criteria (1-10):\n"
            for criterion in rubric:
                rubric_text += f"- {criterion['name']} (weight: {criterion['weight']}): {criterion['description']}\n"

        ranking_prompt = f"""Evaluate these responses to: \"{user_query}\"

{responses_text}
{rubric_text}
For EACH response, provide:
1. Quality rating (1-5)
2. Brief feedback (1 sentence)
{"3. Score per rubric criterion (1-10)" if rubric else ""}

Then provide your FINAL RANKING:
1. Response X (N/5) - brief reason
2. Response Y (N/5) - brief reason
(etc.)"""

        round_results = []

        async def stream_ranking(member: CouncilMember):
            tracker_key = f"s2-{member.member_id}"

            messages = []
            if member.system_prompt:
                messages.append({"role": "system", "content": member.system_prompt})
            messages.append({"role": "user", "content": ranking_prompt})

            content = ""
            ranking_usage = {}
            async for chunk in query_model_streaming(member.model, messages, temperature=temp):
                if chunk["type"] == "token":
                    content = chunk["content"]
                    tps = token_tracker.record_token(tracker_key, chunk["delta"])
                    on_event("stage2_token", {
                        "model": member.model, "member_id": member.member_id,
                        "role": member.role,
                        "delta": chunk["delta"],
                        "content": content, "round": round_num,
                        "tokens_per_second": tps, **token_tracker.get_timing(tracker_key),
                    })
                elif chunk["type"] == "thinking":
                    tps = token_tracker.record_thinking(tracker_key, chunk["delta"])
                    on_event("stage2_thinking", {
                        "model": member.model, "member_id": member.member_id,
                        "delta": chunk["delta"],
                        "round": round_num, "tokens_per_second": tps,
                    })
                elif chunk["type"] == "complete":
                    ranking_usage = chunk.get("usage", {})
                    full_text = chunk["content"]
                    parsed = parse_ranking_from_text(full_text)
                    ratings = extract_quality_ratings(full_text)
                    rubric_criteria = [c["name"] for c in rubric] if rubric else []
                    rubric_scores = extract_rubric_scores(full_text, rubric_criteria)
                    on_event("stage2_model_complete", {
                        "model": member.model, "member_id": member.member_id,
                        "role": member.role,
                        "ranking": full_text,
                        "parsed_ranking": parsed, "quality_ratings": ratings,
                        "rubric_scores": rubric_scores, "round": round_num,
                        "usage": ranking_usage,
                    })
                    return {
                        "model": member.model, "member_id": member.member_id,
                        "role": member.role,
                        "ranking": full_text,
                        "parsed_ranking": parsed, "quality_ratings": ratings,
                        "rubric_scores": rubric_scores, "round": round_num,
                        "usage": ranking_usage,
                    }
                elif chunk["type"] == "error":
                    return None

            if content:
                parsed = parse_ranking_from_text(content)
                ratings = extract_quality_ratings(content)
                return {
                    "model": member.model, "member_id": member.member_id,
                    "role": member.role,
                    "ranking": content,
                    "parsed_ranking": parsed, "quality_ratings": ratings,
                    "round": round_num,
                    "usage": ranking_usage,
                }
            return None

        tasks = [stream_ranking(m) for m in members]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if result and not isinstance(result, Exception):
                round_results.append(result)

        all_rounds_rankings.append(round_results)
        on_event("round_complete", {"round": round_num})

        # Only do 1 round for now
        break

    final_rankings = all_rounds_rankings[-1] if all_rounds_rankings else []

    conflicts = detect_ranking_conflicts(final_rankings, label_to_model)
    minority_opinions = detect_minority_opinions(final_rankings, label_to_model)
    weighted_scores = calculate_weighted_rankings(final_rankings)
    top_label, top_model, top_score = get_top_response(weighted_scores, label_to_model)

    model_scores = {}
    model_score_counts = {}
    for label, score in weighted_scores.items():
        model_id = label_to_model.get(label)
        if model_id:
            if model_id not in model_scores:
                model_scores[model_id] = 0.0
                model_score_counts[model_id] = 0
            model_scores[model_id] += score
            model_score_counts[model_id] += 1
    for mid in model_scores:
        if model_score_counts[mid] > 1:
            model_scores[mid] /= model_score_counts[mid]

    if model_scores and top_model:
        record_deliberation_result(council_id, model_scores, top_model)

    analysis = {
        "conflicts": conflicts,
        "minority_opinions": minority_opinions,
        "weighted_scores": weighted_scores,
        "top_response": {"label": top_label, "model": top_model, "score": top_score},
        "label_to_model": label_to_model,
        "label_to_member": label_to_member,
    }

    return final_rankings, label_to_model, analysis
