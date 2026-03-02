"""Stage 1: Collect individual responses from council members."""

import asyncio
from typing import List, Dict, Any, Optional, Callable

from ..openrouter import query_model_streaming
from ..config_loader import get_response_config, get_council_members, CouncilMember, get_stage_temperatures
from .utils import TokenTracker, strip_fake_images


async def stage1_collect_responses_streaming(
    user_query: str,
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
    panel: Optional[List[Dict[str, str]]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    temperature: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Stage 1: Collect individual responses using council members."""
    response_config = get_response_config()
    response_style = response_config.get("response_style", "standard")
    temp = temperature if temperature is not None else get_stage_temperatures()["stage1"]

    members = get_council_members(council_id, panel=panel)
    results = []
    token_tracker = TokenTracker()

    # Emit init event with total count
    on_event("stage1_init", {"total": len(members)})

    async def stream_member(member: CouncilMember):
        tracker_key = member.member_id

        messages = []
        if member.system_prompt:
            messages.append({"role": "system", "content": member.system_prompt})

        if conversation_history:
            for msg in conversation_history[-6:]:
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

        async for chunk in query_model_streaming(member.model, messages, temperature=temp):
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
