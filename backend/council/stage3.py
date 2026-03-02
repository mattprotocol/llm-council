"""Stage 3: Chairman synthesis of deliberation results."""

from typing import List, Dict, Any, Optional, Callable

from ..openrouter import query_model_streaming
from ..config import CHAIRMAN_MODEL
from ..config_loader import get_response_config, get_stage_temperatures
from ..analysis import format_analysis_summary
from .utils import TokenTracker, strip_fake_images


async def stage3_synthesize_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None],
    council_id: str = "personal",
    analysis: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """Stage 3: Chairman synthesizes from top-voted response."""
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

    temp = temperature if temperature is not None else get_stage_temperatures()["stage3"]
    async for chunk in query_model_streaming(CHAIRMAN_MODEL, messages, temperature=temp):
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
