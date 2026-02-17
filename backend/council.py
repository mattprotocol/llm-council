"""3-stage LLM Council orchestration with multi-council personas and rubric scoring."""

import time
import re
import json
import asyncio
from typing import List, Dict, Any, Tuple, AsyncGenerator, Callable, Optional

from .openrouter import query_models_parallel, query_model_with_retry, query_model_streaming, query_model
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL
from .config_loader import (
    get_deliberation_rounds, get_deliberation_config, get_response_config,
    get_persona_for_model, get_rubric, get_council, get_title_model,
)
from .analysis import (
    detect_ranking_conflicts, detect_minority_opinions,
    calculate_weighted_rankings, get_top_response, format_analysis_summary,
)
from .leaderboard import record_deliberation_result


# ============== Response Post-Processing ==============

def strip_fake_images(text: str) -> str:
    """Remove markdown image references with placeholder/fake URLs."""
    fake_url_patterns = [
        r"!\[[^\]]*\]\(https?://via\.placeholder\.com[^\)]*\)",
        r"!\[[^\]]*\]\(https?://placeholder\.[^\)]*\)",
        r"!\[[^\]]*\]\(https?://example\.com[^\)]*\)",
    ]
    result = text
    for pattern in fake_url_patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ============== Token Tracking ==============

class TokenTracker:
    def __init__(self):
        self.start_times: Dict[str, float] = {}
        self.thinking_end_times: Dict[str, float] = {}
        self.token_counts: Dict[str, int] = {}

    def record_thinking(self, model: str, delta: str = "") -> float:
        now = time.time()
        if model not in self.start_times:
            self.start_times[model] = now
            self.token_counts[model] = 0
        if delta:
            self.token_counts[model] += max(1, len(delta.split()))
        elapsed = now - self.start_times[model]
        return round(self.token_counts[model] / elapsed, 1) if elapsed > 0 else 0.0

    def mark_thinking_done(self, model: str):
        if model not in self.thinking_end_times:
            self.thinking_end_times[model] = time.time()

    def record_token(self, model: str, delta: str) -> float:
        now = time.time()
        if model not in self.start_times:
            self.start_times[model] = now
            self.token_counts[model] = 0
        # Mark transition from thinking to content
        if model not in self.thinking_end_times:
            self.thinking_end_times[model] = now
        self.token_counts[model] += max(1, len(delta.split()))
        elapsed = now - self.start_times[model]
        return round(self.token_counts[model] / elapsed, 1) if elapsed > 0 else 0.0

    def get_timing(self, model: str) -> Dict[str, Any]:
        now = time.time()
        start = self.start_times.get(model, now)
        return {"elapsed_seconds": round(now - start, 1)}

    def get_final_tps(self, model: str) -> float:
        now = time.time()
        start = self.start_times.get(model, now)
        elapsed = now - start
        tokens = self.token_counts.get(model, 0)
        return round(tokens / elapsed, 1) if elapsed > 0 else 0.0

    def get_final_timing(self, model: str) -> Dict[str, Any]:
        now = time.time()
        start = self.start_times.get(model, now)
        return {"total_seconds": round(now - start, 1), "total_tokens": self.token_counts.get(model, 0)}


# ============== JSON Extraction ==============

def _extract_json_from_response(text: str) -> Optional[Dict]:
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from code block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ============== Stage 0: Classification ==============

async def classify_message(user_query: str, on_event: Optional[Callable] = None) -> Dict[str, Any]:
    """Classify message as factual/chat/deliberation."""
    classification_prompt = """Analyze this user message and classify it.

Message: {query}

Respond with ONLY a JSON object:
{{"type": "factual|chat|deliberation", "reasoning": "brief explanation"}}

Rules:
- "factual": Simple questions with definitive answers
- "chat": Greetings, small talk, simple questions
- "deliberation": Opinions, comparisons, complex analysis, subjective questions"""

    messages = [{"role": "user", "content": classification_prompt.format(query=user_query)}]
    title_model = get_title_model()

    try:
        response = await query_model_with_retry(title_model, messages, timeout=30.0, max_retries=1, temperature=0.0)
        if not response or not response.get("content"):
            return {"type": "deliberation", "reasoning": "Classification failed"}

        result = _extract_json_from_response(response["content"].strip())
        if result and "type" in result:
            if result["type"] not in ["factual", "chat", "deliberation"]:
                result["type"] = "deliberation"
            return result

        return {"type": "deliberation", "reasoning": "Parse failed"}
    except Exception as e:
        return {"type": "deliberation", "reasoning": f"Error: {str(e)[:30]}"}


# ============== Chairman Direct Response ==============

async def chairman_direct_response(
    user_query: str,
    tool_result: Optional[Dict[str, Any]] = None,
    on_event: Optional[Callable] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate a direct response from the chairman without deliberation."""
    messages = []
    if conversation_history:
        for msg in conversation_history[-6:]:
            if msg.get("role") == "user":
                messages.append({"role": "user", "content": msg["content"]})
            elif msg.get("role") == "assistant":
                s3 = msg.get("stage3", {})
                if isinstance(s3, dict) and s3.get("response"):
                    messages.append({"role": "assistant", "content": s3["response"]})

    messages.append({"role": "user", "content": user_query})

    response = await query_model_with_retry(CHAIRMAN_MODEL, messages, timeout=60.0)
    if response and response.get("content"):
        return {"model": CHAIRMAN_MODEL, "response": response["content"]}
    return {"model": CHAIRMAN_MODEL, "response": "I apologize, I was unable to generate a response."}


# ============== Ranking Parser ==============

def parse_ranking_from_text(text: str) -> List[str]:
    """Parse response labels from ranking text."""
    labels = []
    # Look for FINAL RANKING section
    final_match = re.search(r"FINAL RANKING[:\s]*(.+)", text, re.DOTALL | re.IGNORECASE)
    search_text = final_match.group(1) if final_match else text

    # Match patterns like "1. Response A" or "1. A"
    pattern = r"(?:^|\n)\s*\d+\.\s*(?:Response\s+)?([A-Z])"
    matches = re.findall(pattern, search_text, re.IGNORECASE)
    for m in matches:
        label = f"Response {m.upper()}"
        if label not in labels:
            labels.append(label)
    return labels


def extract_quality_ratings(text: str) -> Dict[str, float]:
    """Extract quality ratings from ranking text."""
    ratings = {}
    pattern = r"(?:Response\s+)?([A-Z])\s*[:\(]\s*(\d+(?:\.\d+)?)\s*/\s*(?:5|10)"
    for match in re.finditer(pattern, text, re.IGNORECASE):
        label = f"Response {match.group(1).upper()}"
        score = float(match.group(2))
        if score > 5:
            score = score / 2  # Normalize 10-scale to 5-scale
        ratings[label] = score
    return ratings


def extract_rubric_scores(text: str, rubric_criteria: List[str]) -> Dict[str, Dict[str, float]]:
    """Extract per-criterion rubric scores from ranking text."""
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
    """Calculate aggregate rankings from individual model rankings."""
    scores = {}
    for ranking in rankings:
        parsed = ranking.get("parsed_ranking", [])
        for i, label in enumerate(parsed):
            if label not in scores:
                scores[label] = 0
            scores[label] += len(parsed) - i
    sorted_labels = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return {label: rank + 1 for rank, (label, _) in enumerate(sorted_labels)}


# ============== Stage 1: Collect Responses (Streaming) ==============

async def stage1_collect_responses_streaming(
    user_query: str,
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
) -> List[Dict[str, Any]]:
    """Stage 1: Collect individual responses with persona system prompts."""
    response_config = get_response_config()
    response_style = response_config.get("response_style", "standard")

    results = []
    token_tracker = TokenTracker()

    async def stream_model(model: str):
        persona = get_persona_for_model(council_id, model)
        system_prompt = None
        role_name = model.split("/")[-1]

        if persona:
            role_name = persona.get("role", role_name)
            system_prompt = persona.get("prompt", "")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if response_style == "concise":
            messages.append({"role": "user", "content": f"Answer concisely and directly:\n\n{user_query}"})
        else:
            messages.append({"role": "user", "content": user_query})

        content = ""
        reasoning = ""

        async for chunk in query_model_streaming(model, messages):
            if chunk["type"] == "token":
                content = chunk["content"]
                tps = token_tracker.record_token(model, chunk["delta"])
                on_event("stage1_token", {
                    "model": model, "role": role_name,
                    "delta": chunk["delta"], "content": content,
                    "tokens_per_second": tps, **token_tracker.get_timing(model),
                })
            elif chunk["type"] == "thinking":
                reasoning = chunk["content"]
                tps = token_tracker.record_thinking(model, chunk["delta"])
                on_event("stage1_thinking", {
                    "model": model, "role": role_name,
                    "delta": chunk["delta"], "thinking": reasoning,
                    "tokens_per_second": tps, **token_tracker.get_timing(model),
                })
            elif chunk["type"] == "complete":
                final = chunk["content"]
                if not final and chunk.get("reasoning_content"):
                    final = chunk["reasoning_content"]
                final = strip_fake_images(final)
                on_event("stage1_model_complete", {
                    "model": model, "role": role_name,
                    "response": final,
                    "tokens_per_second": token_tracker.get_final_tps(model),
                    **token_tracker.get_final_timing(model),
                })
                return {"model": model, "role": role_name, "response": final}
            elif chunk["type"] == "error":
                on_event("stage1_model_error", {"model": model, "error": chunk["error"]})
                return None

        if content:
            content = strip_fake_images(content)
            return {"model": model, "role": role_name, "response": content}
        return None

    tasks = [stream_model(m) for m in COUNCIL_MODELS]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for resp in responses:
        if resp and not isinstance(resp, Exception):
            results.append(resp)

    return results


# ============== Stage 2: Rankings with Rubric Scoring (Streaming) ==============

async def stage2_collect_rankings_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """Stage 2: Multi-round deliberation with rubric-based scoring."""
    deliberation_config = get_deliberation_config()
    max_rounds = deliberation_config.get("max_rounds", 3)
    rubric = get_rubric(council_id)

    # Create anonymized labels
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    label_to_model = {
        f"Response {label}": result["model"]
        for label, result in zip(labels, stage1_results)
    }

    current_responses = {
        f"Response {label}": result["response"]
        for label, result in zip(labels, stage1_results)
    }

    all_rounds_rankings = []
    token_tracker = TokenTracker()

    for round_num in range(1, max_rounds + 1):
        on_event("round_start", {"round": round_num, "max_rounds": max_rounds})

        responses_text = "\n\n".join([
            f"{label}:\n{response}" for label, response in current_responses.items()
        ])

        # Build rubric-based ranking prompt
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

        messages = [{"role": "user", "content": ranking_prompt}]
        round_results = []

        async def stream_ranking(model: str):
            content = ""
            async for chunk in query_model_streaming(model, messages):
                if chunk["type"] == "token":
                    content = chunk["content"]
                    tps = token_tracker.record_token(model, chunk["delta"])
                    on_event("stage2_token", {
                        "model": model, "delta": chunk["delta"],
                        "content": content, "round": round_num,
                        "tokens_per_second": tps, **token_tracker.get_timing(model),
                    })
                elif chunk["type"] == "thinking":
                    tps = token_tracker.record_thinking(model, chunk["delta"])
                    on_event("stage2_thinking", {
                        "model": model, "delta": chunk["delta"],
                        "round": round_num, "tokens_per_second": tps,
                    })
                elif chunk["type"] == "complete":
                    full_text = chunk["content"]
                    parsed = parse_ranking_from_text(full_text)
                    ratings = extract_quality_ratings(full_text)
                    rubric_criteria = [c["name"] for c in rubric] if rubric else []
                    rubric_scores = extract_rubric_scores(full_text, rubric_criteria)
                    on_event("stage2_model_complete", {
                        "model": model, "ranking": full_text,
                        "parsed_ranking": parsed, "quality_ratings": ratings,
                        "rubric_scores": rubric_scores, "round": round_num,
                    })
                    return {
                        "model": model, "ranking": full_text,
                        "parsed_ranking": parsed, "quality_ratings": ratings,
                        "rubric_scores": rubric_scores, "round": round_num,
                    }
                elif chunk["type"] == "error":
                    return None

            if content:
                parsed = parse_ranking_from_text(content)
                ratings = extract_quality_ratings(content)
                return {
                    "model": model, "ranking": content,
                    "parsed_ranking": parsed, "quality_ratings": ratings,
                    "round": round_num,
                }
            return None

        tasks = [stream_ranking(m) for m in COUNCIL_MODELS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if result and not isinstance(result, Exception):
                round_results.append(result)

        all_rounds_rankings.append(round_results)
        on_event("round_complete", {"round": round_num})

        # Only do 1 round for now (multi-round refinement can be added later)
        break

    # Flatten rankings from all rounds (use last round)
    final_rankings = all_rounds_rankings[-1] if all_rounds_rankings else []

    # Analysis: detect conflicts and minority opinions
    conflicts = detect_ranking_conflicts(final_rankings, label_to_model)
    minority_opinions = detect_minority_opinions(final_rankings, label_to_model)
    weighted_scores = calculate_weighted_rankings(final_rankings)
    top_label, top_model, top_score = get_top_response(weighted_scores, label_to_model)

    # Record to leaderboard
    model_scores = {}
    for label, score in weighted_scores.items():
        model_id = label_to_model.get(label)
        if model_id:
            model_scores[model_id] = score
    if model_scores and top_model:
        record_deliberation_result(council_id, model_scores, top_model)

    analysis = {
        "conflicts": conflicts,
        "minority_opinions": minority_opinions,
        "weighted_scores": weighted_scores,
        "top_response": {"label": top_label, "model": top_model, "score": top_score},
        "label_to_model": label_to_model,
    }

    return final_rankings, label_to_model, analysis


# ============== Stage 3: Chairman Synthesis (Streaming) ==============

async def stage3_synthesize_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Stage 3: Chairman synthesizes from top-voted response (reduced influence)."""
    response_config = get_response_config()

    # Build context
    stage1_text = "\n\n".join([
        f"Model: {r['model']} (Role: {r.get('role', 'N/A')})\nResponse: {r['response']}"
        for r in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Evaluator: {r['model']}\nRanking: {r['ranking']}"
        for r in stage2_results if isinstance(r, dict)
    ])

    # Include analysis summary for chairman
    analysis_text = ""
    if analysis:
        analysis_text = format_analysis_summary(
            analysis.get("conflicts", []),
            analysis.get("minority_opinions", []),
            analysis.get("weighted_scores", {}),
        )

    # Reduced chairman influence: synthesize from top-voted, don't pick independently
    top_info = ""
    if analysis and analysis.get("top_response"):
        top = analysis["top_response"]
        top_label = top.get("label", "")
        for r in stage1_results:
            if r["model"] == top.get("model"):
                top_info = f"\n\nTOP-VOTED RESPONSE ({top_label}, score: {top.get('score', 0):.1f}):\n{r['response']}"
                break

    chairman_prompt = f"""You are the Presenter of an LLM Council. Your job is to EDIT AND REFINE the top-voted response, incorporating the strongest points from other responses.

IMPORTANT: Do NOT write a completely new response. Start from the top-voted response and improve it.

Original Question: {user_query}

{analysis_text}
{top_info}

ALL Council Responses:
{stage1_text}

Peer Rankings:
{stage2_text}

Instructions:
1. Start from the top-voted response as your base
2. Incorporate the strongest unique points from other responses
3. Address any flagged minority opinions if they have merit
4. Note any significant conflicts between models
5. Use rich markdown formatting (headers, tables, lists, bold, code blocks)
6. DO NOT include images or image links

Provide the refined, synthesized final answer:"""

    messages = [{"role": "user", "content": chairman_prompt}]
    content = ""
    reasoning = ""
    token_tracker = TokenTracker()

    async for chunk in query_model_streaming(CHAIRMAN_MODEL, messages):
        if chunk["type"] == "token":
            content = chunk["content"]
            tps = token_tracker.record_token(CHAIRMAN_MODEL, chunk["delta"])
            on_event("stage3_token", {
                "model": CHAIRMAN_MODEL, "delta": chunk["delta"],
                "content": content, "tokens_per_second": tps,
                **token_tracker.get_timing(CHAIRMAN_MODEL),
            })
        elif chunk["type"] == "thinking":
            reasoning = chunk["content"]
            tps = token_tracker.record_thinking(CHAIRMAN_MODEL, chunk["delta"])
            on_event("stage3_thinking", {
                "model": CHAIRMAN_MODEL, "delta": chunk["delta"],
                "thinking": reasoning, "tokens_per_second": tps,
            })
        elif chunk["type"] == "complete":
            final = chunk["content"]
            if not final and chunk.get("reasoning_content"):
                final = chunk["reasoning_content"]
            final = strip_fake_images(final)
            on_event("stage3_complete", {
                "model": CHAIRMAN_MODEL, "response": final,
                "tokens_per_second": token_tracker.get_final_tps(CHAIRMAN_MODEL),
                **token_tracker.get_final_timing(CHAIRMAN_MODEL),
            })
            return {"model": CHAIRMAN_MODEL, "response": final}
        elif chunk["type"] == "error":
            on_event("stage3_error", {"model": CHAIRMAN_MODEL, "error": chunk["error"]})
            return {"model": CHAIRMAN_MODEL, "response": strip_fake_images(content) if content else "Error: Unable to generate synthesis."}

    return {"model": CHAIRMAN_MODEL, "response": strip_fake_images(content) if content else "Error: Unable to generate synthesis."}
