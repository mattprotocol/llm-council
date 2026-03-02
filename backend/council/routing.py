"""Stage 0: Message classification and advisor routing."""

from typing import List, Dict, Any, Tuple, Optional, Callable

from ..openrouter import query_model_with_retry
from ..config import CHAIRMAN_MODEL
from ..config_loader import (
    get_title_model, get_advisors, get_advisor_roster_summary,
    get_routing_config, get_council_models,
)
from .utils import extract_json_from_response, strip_fake_images


def _is_followup_heuristic(query: str, has_history: bool) -> Optional[Dict[str, Any]]:
    """Fast heuristic check for obvious follow-up messages."""
    if not has_history:
        return None

    query_lower = query.lower().strip()

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

    if len(query_lower.split()) <= 15:
        context_pronouns = ["that", "this", "it", "them", "those", "these"]
        words = query_lower.split()
        for pronoun in context_pronouns:
            if pronoun in words:
                if not any(w in query_lower for w in ["what is a", "what is an", "define ", "who is "]):
                    return {"type": "followup", "reasoning": f"Heuristic: short message with context-dependent pronoun '{pronoun}'", "usage": {}}

    return None


async def classify_message(
    user_query: str,
    on_event: Optional[Callable] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify message as factual/chat/deliberation/followup."""
    has_history = bool(conversation_history and len(conversation_history) > 0)
    heuristic = _is_followup_heuristic(user_query, has_history)
    if heuristic:
        return heuristic

    history_context = ""
    if conversation_history:
        recent = conversation_history[-4:]
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
- "followup": The message references prior conversation. If the message only makes sense WITH prior context, it is a followup.
- "factual": Simple NEW questions with definitive answers (self-contained)
- "chat": Greetings, small talk, simple acknowledgments
- "deliberation": New complex questions requiring multiple perspectives (self-contained)"""

    messages = [{"role": "user", "content": classification_prompt.format(query=user_query, history=history_context)}]
    title_model = get_title_model()

    try:
        response = await query_model_with_retry(title_model, messages, timeout=30.0, max_retries=1, temperature=0.0)
        if not response or not response.get("content"):
            return {"type": "deliberation", "reasoning": "Classification failed", "usage": {}}

        result = extract_json_from_response(response["content"].strip())
        if result and "type" in result:
            if result["type"] not in ["factual", "chat", "deliberation", "followup"]:
                result["type"] = "deliberation"
            result["usage"] = response.get("usage", {})
            return result

        return {"type": "deliberation", "reasoning": "Parse failed", "usage": response.get("usage", {})}
    except Exception as e:
        return {"type": "deliberation", "reasoning": f"Error: {str(e)[:30]}", "usage": {}}


async def stage0_route_question(
    user_query: str,
    council_id: str,
    on_event: Optional[Callable] = None,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Route a question to the most relevant advisors from the council roster."""
    advisors = get_advisor_roster_summary(council_id)
    if not advisors:
        return [], {}

    routing_config = get_routing_config(council_id)
    min_advisors = routing_config.get("min_advisors", 3)
    max_advisors = routing_config.get("max_advisors", 5)
    default_advisors = routing_config.get("default_advisors", 5)
    all_models = get_council_models()

    roster_lines = []
    for a in advisors:
        tags_str = ", ".join(a.get("tags", []))
        roster_lines.append(f"- {a['id']}: {a['name']} \u2014 {a.get('role', '')} [tags: {tags_str}]")
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
2. Select {min_advisors}-{max_advisors} advisors whose expertise best matches the question.
3. Assign each selected advisor a model from the available list. Distribute models across advisors.
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

        result = extract_json_from_response(response["content"].strip())
        if not result or "panel" not in result:
            return _fallback_panel(advisors, all_models, default_advisors), routing_usage

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
