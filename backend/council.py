"""3-stage LLM Council orchestration with dynamic advisor routing."""

import time
import re
import json
import asyncio
from typing import List, Dict, Any, Tuple, AsyncGenerator, Callable, Optional

from .openrouter import query_models_parallel, query_model_with_retry, query_model_streaming, query_model
from .config import CHAIRMAN_MODEL
from .config_loader import (
    get_deliberation_rounds, get_deliberation_config, get_response_config,
    get_rubric, get_council, get_title_model, get_council_members, CouncilMember,
    get_advisors, get_advisor_roster_summary, get_routing_config, get_council_models,
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

    def record_thinking(self, key: str, delta: str = "") -> float:
        now = time.time()
        if key not in self.start_times:
            self.start_times[key] = now
            self.token_counts[key] = 0
        if delta:
            self.token_counts[key] += max(1, len(delta.split()))
        elapsed = now - self.start_times[key]
        return round(self.token_counts[key] / elapsed, 1) if elapsed > 0 else 0.0

    def mark_thinking_done(self, key: str):
        if key not in self.thinking_end_times:
            self.thinking_end_times[key] = time.time()

    def record_token(self, key: str, delta: str) -> float:
        now = time.time()
        if key not in self.start_times:
            self.start_times[key] = now
            self.token_counts[key] = 0
        if key not in self.thinking_end_times:
            self.thinking_end_times[key] = now
        self.token_counts[key] += max(1, len(delta.split()))
        elapsed = now - self.start_times[key]
        return round(self.token_counts[key] / elapsed, 1) if elapsed > 0 else 0.0

    def get_timing(self, key: str) -> Dict[str, Any]:
        now = time.time()
        start = self.start_times.get(key, now)
        return {"elapsed_seconds": round(now - start, 1)}

    def get_final_tps(self, key: str) -> float:
        now = time.time()
        start = self.start_times.get(key, now)
        elapsed = now - start
        tokens = self.token_counts.get(key, 0)
        return round(tokens / elapsed, 1) if elapsed > 0 else 0.0

    def get_final_timing(self, key: str) -> Dict[str, Any]:
        now = time.time()
        start = self.start_times.get(key, now)
        return {"total_seconds": round(now - start, 1), "total_tokens": self.token_counts.get(key, 0)}


# ============== Usage Aggregation ==============

class UsageAggregator:
    """Aggregates token usage and costs across multiple API calls."""
    def __init__(self):
        self.calls = []

    def record(self, stage: str, model: str, usage: dict, member_id: str = ""):
        if usage:
            self.calls.append({
                "stage": stage, "model": model,
                "member_id": member_id, "usage": usage,
            })

    def get_stage_summary(self, stage: str) -> dict:
        stage_calls = [c for c in self.calls if c["stage"] == stage]
        return {
            "prompt_tokens": sum(c["usage"].get("prompt_tokens", 0) for c in stage_calls),
            "completion_tokens": sum(c["usage"].get("completion_tokens", 0) for c in stage_calls),
            "total_tokens": sum(c["usage"].get("total_tokens", 0) for c in stage_calls),
            "cost": sum(c["usage"].get("cost", 0) for c in stage_calls),
            "calls": len(stage_calls),
        }

    def get_total(self) -> dict:
        return {
            "prompt_tokens": sum(c["usage"].get("prompt_tokens", 0) for c in self.calls),
            "completion_tokens": sum(c["usage"].get("completion_tokens", 0) for c in self.calls),
            "total_tokens": sum(c["usage"].get("total_tokens", 0) for c in self.calls),
            "cost": sum(c["usage"].get("cost", 0) for c in self.calls),
            "calls": len(self.calls),
        }

    def get_breakdown(self) -> dict:
        stages = sorted(set(c["stage"] for c in self.calls))
        return {
            "by_stage": {s: self.get_stage_summary(s) for s in stages},
            "total": self.get_total(),
        }


# ============== JSON Extraction ==============

def _extract_json_from_response(text: str) -> Optional[Dict]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ============== Stage 0: Classification ==============

def _is_followup_heuristic(query: str, has_history: bool) -> Optional[Dict[str, Any]]:
    """Fast heuristic check for obvious follow-up messages.

    Returns a classification dict if confidently a follow-up, None otherwise.
    """
    if not has_history:
        return None

    query_lower = query.lower().strip()

    # Explicit follow-up signals
    followup_phrases = [
        "follow up", "followup", "follow-up",
        "as i said", "as i mentioned", "as we discussed",
        "what you said", "what you mentioned", "you said",
        "you mentioned", "you suggested", "you recommended",
        "all of this", "all of that", "incorporate the above",
        "based on this", "based on that", "based on what",
        "can you summarize", "can you consolidate",
        "going back to", "regarding what", "about what you",
        "the above", "from above", "mentioned earlier",
        "earlier you", "previously you", "you just said",
        "expand on", "elaborate on", "more about",
        "what about", "how about", "and what about",
        "can you also", "one more thing",
        "thanks, now", "ok, now", "great, now",
        "ok now", "ok so", "ok can you",
        "also,", "also can you",
    ]

    for phrase in followup_phrases:
        if phrase in query_lower:
            return {"type": "followup", "reasoning": f"Heuristic: contains '{phrase}'", "usage": {}}

    # Short messages with pronouns that need prior context
    if len(query_lower.split()) <= 15:
        context_pronouns = ["that", "this", "it", "them", "those", "these"]
        words = query_lower.split()
        for pronoun in context_pronouns:
            if pronoun in words:
                # Check it's not a self-contained question like "what is that thing called a..."
                if not any(w in query_lower for w in ["what is a", "what is an", "define ", "who is "]):
                    return {"type": "followup", "reasoning": f"Heuristic: short message with context-dependent pronoun '{pronoun}'", "usage": {}}

    return None


async def classify_message(
    user_query: str,
    on_event: Optional[Callable] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify message as factual/chat/deliberation/followup."""
    # Fast heuristic check first — catches obvious follow-ups without an LLM call
    has_history = bool(conversation_history and len(conversation_history) > 0)
    heuristic = _is_followup_heuristic(user_query, has_history)
    if heuristic:
        return heuristic

    # Build context from history so LLM classifier can detect subtler follow-ups
    history_context = ""
    if conversation_history:
        recent = conversation_history[-4:]  # Last 2 exchanges
        history_lines = []
        for msg in recent:
            if msg.get("role") == "user":
                history_lines.append(f"User: {msg['content'][:200]}")
            elif msg.get("role") == "assistant":
                s3 = msg.get("stage3", {})
                if isinstance(s3, dict) and s3.get("response"):
                    history_lines.append(f"Assistant: {s3['response'][:200]}")
        if history_lines:
            history_context = "\n\nRecent conversation history:\n" + "\n".join(history_lines)

    classification_prompt = """Analyze this user message and classify it.

Message: {query}{history}

Respond with ONLY a JSON object:
{{"type": "factual|chat|deliberation|followup", "reasoning": "brief explanation"}}

Rules:
- "followup": The message references prior conversation (e.g. "all of this", "what you said", "can you summarize", "incorporate the above", "based on this", or pronouns referring to earlier content). If the message only makes sense WITH prior context, it is a followup. This is the most important classification — when in doubt between followup and deliberation, choose followup.
- "factual": Simple NEW questions with definitive answers (self-contained, no prior context needed)
- "chat": Greetings, small talk, simple acknowledgments
- "deliberation": New complex questions requiring multiple perspectives (self-contained, does NOT reference prior conversation)"""

    messages = [{"role": "user", "content": classification_prompt.format(query=user_query, history=history_context)}]
    title_model = get_title_model()

    try:
        response = await query_model_with_retry(title_model, messages, timeout=30.0, max_retries=1, temperature=0.0)
        if not response or not response.get("content"):
            return {"type": "deliberation", "reasoning": "Classification failed", "usage": {}}

        result = _extract_json_from_response(response["content"].strip())
        if result and "type" in result:
            if result["type"] not in ["factual", "chat", "deliberation", "followup"]:
                result["type"] = "deliberation"
            result["usage"] = response.get("usage", {})
            return result

        return {"type": "deliberation", "reasoning": "Parse failed", "usage": response.get("usage", {})}
    except Exception as e:
        return {"type": "deliberation", "reasoning": f"Error: {str(e)[:30]}", "usage": {}}


# ============== Stage 0b: Route Question (NEW) ==============

async def stage0_route_question(
    user_query: str,
    council_id: str,
    on_event: Optional[Callable] = None,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Route a question to the most relevant advisors from the council roster.

    Returns a tuple of (panel, usage):
      - panel: list of {"advisor_id": ..., "model": ..., "reasoning": ...}
      - usage: usage dict from the routing API call
    """
    advisors = get_advisor_roster_summary(council_id)
    if not advisors:
        return [], {}

    routing_config = get_routing_config(council_id)
    min_advisors = routing_config.get("min_advisors", 3)
    max_advisors = routing_config.get("max_advisors", 5)
    default_advisors = routing_config.get("default_advisors", 5)
    all_models = get_council_models()

    # Build roster description for the router
    roster_lines = []
    for a in advisors:
        tags_str = ", ".join(a.get("tags", []))
        roster_lines.append(f"- {a['id']}: {a['name']} — {a.get('role', '')} [tags: {tags_str}]")
    roster_text = "\n".join(roster_lines)

    models_text = "\n".join([f"- {m}" for m in all_models])

    router_prompt = f"""You are a question router for an advisory council. Given a user's question and a roster of available advisors, select the {min_advisors}-{max_advisors} most relevant advisors and assign each a model.

USER QUESTION:
{user_query}

AVAILABLE ADVISORS:
{roster_text}

AVAILABLE MODELS:
{models_text}

INSTRUCTIONS:
1. Analyze the question to identify key topics, domains, and needs.
2. Select {min_advisors}-{max_advisors} advisors whose expertise best matches the question. Pick fewer (closer to {min_advisors}) for focused questions, more (closer to {max_advisors}) for broad/complex ones.
3. Assign each selected advisor a model from the available list. Try to distribute models across advisors (avoid giving all advisors the same model). Use different models when possible.
4. Briefly explain why each advisor was selected.

Respond with ONLY a JSON object:
{{
  "panel": [
    {{"advisor_id": "id-here", "model": "model/id-here", "reasoning": "brief reason"}},
    ...
  ],
  "routing_reasoning": "1-2 sentence overall explanation"
}}"""

    messages = [{"role": "user", "content": router_prompt}]
    title_model = get_title_model()

    try:
        response = await query_model_with_retry(
            title_model, messages, timeout=30.0, max_retries=1, temperature=0.3
        )
        routing_usage = response.get("usage", {}) if response else {}

        if not response or not response.get("content"):
            return _fallback_panel(advisors, all_models, default_advisors), routing_usage

        result = _extract_json_from_response(response["content"].strip())
        if not result or "panel" not in result:
            return _fallback_panel(advisors, all_models, default_advisors), routing_usage

        # Validate panel
        panel = result["panel"]
        valid_advisor_ids = {a["id"] for a in advisors}
        valid_model_ids = set(all_models)
        validated = []

        for item in panel:
            aid = item.get("advisor_id", "")
            model = item.get("model", "")
            if aid not in valid_advisor_ids:
                continue
            if model not in valid_model_ids:
                model = all_models[len(validated) % len(all_models)]
            validated.append({
                "advisor_id": aid,
                "model": model,
                "reasoning": item.get("reasoning", ""),
            })

        if len(validated) < min_advisors:
            return _fallback_panel(advisors, all_models, default_advisors), routing_usage

        # Trim to max
        validated = validated[:max_advisors]

        return validated, routing_usage

    except Exception as e:
        print(f"Router error: {e}")
        return _fallback_panel(advisors, all_models, default_advisors), {}


def _fallback_panel(
    advisors: List[Dict[str, Any]],
    models: List[str],
    count: int,
) -> List[Dict[str, str]]:
    """Deterministic fallback: first N advisors with round-robin model assignment."""
    panel = []
    for i, a in enumerate(advisors[:count]):
        panel.append({
            "advisor_id": a["id"],
            "model": models[i % len(models)],
            "reasoning": "fallback selection",
        })
    return panel


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
        return {"model": CHAIRMAN_MODEL, "response": response["content"], "usage": response.get("usage", {})}
    return {"model": CHAIRMAN_MODEL, "response": "I apologize, I was unable to generate a response.", "usage": {}}


# ============== Ranking Parser ==============

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


# ============== Stage 1: Collect Responses (Streaming) ==============

async def stage1_collect_responses_streaming(
    user_query: str,
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
    panel: Optional[List[Dict[str, str]]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Stage 1: Collect individual responses using council members.

    Args:
        panel: Optional list of {"advisor_id": ..., "model": ...} from router.
               If provided, only these advisors respond with specified models.
        conversation_history: Prior conversation messages for multi-turn context.
    """
    response_config = get_response_config()
    response_style = response_config.get("response_style", "standard")

    members = get_council_members(council_id, panel=panel)
    results = []
    token_tracker = TokenTracker()

    async def stream_member(member: CouncilMember):
        tracker_key = member.member_id

        messages = []
        if member.system_prompt:
            messages.append({"role": "system", "content": member.system_prompt})

        # Include conversation history for multi-turn context
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 3 exchanges
                if msg.get("role") == "user":
                    messages.append({"role": "user", "content": msg["content"]})
                elif msg.get("role") == "assistant":
                    s3 = msg.get("stage3", {})
                    if isinstance(s3, dict) and s3.get("response"):
                        messages.append({"role": "assistant", "content": s3["response"]})

        if response_style == "concise":
            messages.append({"role": "user", "content": f"Answer concisely and directly:\n\n{user_query}"})
        else:
            messages.append({"role": "user", "content": user_query})

        content = ""
        reasoning = ""
        member_usage = {}

        async for chunk in query_model_streaming(member.model, messages):
            if chunk["type"] == "token":
                content = chunk["content"]
                tps = token_tracker.record_token(tracker_key, chunk["delta"])
                on_event("stage1_token", {
                    "model": member.model, "role": member.role,
                    "member_id": member.member_id,
                    "delta": chunk["delta"], "content": content,
                    "tokens_per_second": tps, **token_tracker.get_timing(tracker_key),
                })
            elif chunk["type"] == "thinking":
                reasoning = chunk["content"]
                tps = token_tracker.record_thinking(tracker_key, chunk["delta"])
                on_event("stage1_thinking", {
                    "model": member.model, "role": member.role,
                    "member_id": member.member_id,
                    "delta": chunk["delta"], "thinking": reasoning,
                    "tokens_per_second": tps, **token_tracker.get_timing(tracker_key),
                })
            elif chunk["type"] == "complete":
                member_usage = chunk.get("usage", {})
                final = chunk["content"]
                if not final and chunk.get("reasoning_content"):
                    final = chunk["reasoning_content"]
                final = strip_fake_images(final)
                on_event("stage1_model_complete", {
                    "model": member.model, "role": member.role,
                    "member_id": member.member_id,
                    "response": final,
                    "usage": member_usage,
                    "tokens_per_second": token_tracker.get_final_tps(tracker_key),
                    **token_tracker.get_final_timing(tracker_key),
                })
                return {
                    "model": member.model, "role": member.role,
                    "member_id": member.member_id,
                    "response": final,
                    "usage": member_usage,
                }
            elif chunk["type"] == "error":
                on_event("stage1_model_error", {
                    "model": member.model, "member_id": member.member_id,
                    "error": chunk["error"],
                })
                return None

        if content:
            content = strip_fake_images(content)
            return {
                "model": member.model, "role": member.role,
                "member_id": member.member_id,
                "response": content,
                "usage": member_usage,
            }
        return None

    tasks = [stream_member(m) for m in members]
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
    panel: Optional[List[Dict[str, str]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """Stage 2: Multi-round deliberation with rubric-based scoring.

    Uses the same panel members as Stage 1 for evaluation.
    """
    deliberation_config = get_deliberation_config()
    max_rounds = deliberation_config.get("max_rounds", 3)
    rubric = get_rubric(council_id)
    members = get_council_members(council_id, panel=panel)

    # Create anonymized labels
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
            async for chunk in query_model_streaming(member.model, messages):
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

    # Record to leaderboard
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


# ============== Stage 3: Chairman Synthesis (Streaming) ==============

async def stage3_synthesize_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
    analysis: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Stage 3: Chairman synthesizes from top-voted response."""
    response_config = get_response_config()

    # Build context — use advisor names for attribution
    stage1_text = "\n\n".join([
        f"{r.get('role', r['model'])} ({r['model']}):\nResponse: {r['response']}"
        for r in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Evaluator: {r.get('role', r['model'])} ({r['model']})\nRanking: {r['ranking']}"
        for r in stage2_results if isinstance(r, dict)
    ])

    analysis_text = ""
    if analysis:
        analysis_text = format_analysis_summary(
            analysis.get("conflicts", []),
            analysis.get("minority_opinions", []),
            analysis.get("weighted_scores", {}),
        )

    top_info = ""
    if analysis and analysis.get("top_response"):
        top = analysis["top_response"]
        top_label = top.get("label", "")
        label_to_member = analysis.get("label_to_member", {})
        top_member = label_to_member.get(top_label, {})
        top_role = top_member.get("role", top.get("model", ""))
        for r in stage1_results:
            member_id = r.get("member_id", "")
            if member_id and member_id == top_member.get("member_id"):
                top_info = f"\n\nTOP-VOTED RESPONSE from {top_role} ({top_label}, score: {top.get('score', 0):.1f}):\n{r['response']}"
                break
            elif r["model"] == top.get("model"):
                top_info = f"\n\nTOP-VOTED RESPONSE from {r.get('role', r['model'])} ({top_label}, score: {top.get('score', 0):.1f}):\n{r['response']}"
                break

    # Build conversation history context for the chairman
    history_context = ""
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-6:]:
            if msg.get("role") == "user":
                history_lines.append(f"User: {msg['content'][:500]}")
            elif msg.get("role") == "assistant":
                s3 = msg.get("stage3", {})
                if isinstance(s3, dict) and s3.get("response"):
                    history_lines.append(f"Assistant: {s3['response'][:500]}")
        if history_lines:
            history_context = "\n\nPrior Conversation Context:\n" + "\n\n".join(history_lines) + "\n"

    chairman_prompt = f"""You are the Presenter of an LLM Council. Your job is to EDIT AND REFINE the top-voted response, incorporating the strongest points from other responses.

IMPORTANT: Do NOT write a completely new response. Start from the top-voted response and improve it.
{history_context}
Current Question: {user_query}

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
    stage3_usage = {}

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
            stage3_usage = chunk.get("usage", {})
            final = chunk["content"]
            if not final and chunk.get("reasoning_content"):
                final = chunk["reasoning_content"]
            final = strip_fake_images(final)
            on_event("stage3_complete", {
                "model": CHAIRMAN_MODEL, "response": final,
                "usage": stage3_usage,
                "tokens_per_second": token_tracker.get_final_tps(CHAIRMAN_MODEL),
                **token_tracker.get_final_timing(CHAIRMAN_MODEL),
            })
            return {"model": CHAIRMAN_MODEL, "response": final, "usage": stage3_usage}
        elif chunk["type"] == "error":
            on_event("stage3_error", {"model": CHAIRMAN_MODEL, "error": chunk["error"]})
            return {"model": CHAIRMAN_MODEL, "response": strip_fake_images(content) if content else "Error: Unable to generate synthesis.", "usage": stage3_usage}

    return {"model": CHAIRMAN_MODEL, "response": strip_fake_images(content) if content else "Error: Unable to generate synthesis.", "usage": stage3_usage}
