"""FastAPI backend for multi-council LLM deliberation."""

import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
import uuid
import json
import asyncio

from . import storage
from .council import (
    classify_message,
    chairman_direct_response,
    stage0_route_question,
    stage1_collect_responses_streaming,
    stage2_collect_rankings_streaming,
    stage3_synthesize_streaming,
    calculate_aggregate_rankings,
    UsageAggregator,
)
from .config_loader import (
    load_config,
    load_councils,
    get_councils_summary,
    get_council,
    get_council_models,
    get_title_model,
    save_models_config,
    save_council_config,
    delete_council_config,
    reload_config,
    get_advisors,
    get_advisor_roster_summary,
    get_routing_config,
    get_stage_temperatures,
)  # reload_config used for import/export
from .config import reload_runtime_config
from .leaderboard import get_council_leaderboard, get_all_leaderboards, get_advisor_leaderboard, get_all_advisor_leaderboards, record_deliberation_result, record_advisor_selection
from .search import detect_search_intent, search, get_search_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifespan events."""
    print("Starting LLM Council API...")
    config = load_config()
    councils = load_councils()
    models = get_council_models()
    print(f"Loaded {len(councils)} councils: {list(councils.keys())}")
    print(f"Council models: {models}")

    try:
        from .openrouter import validate_openrouter_models
        availability = await validate_openrouter_models(models)
        for mid, available in availability.items():
            status = "available" if available else "NOT FOUND"
            print(f"  {mid}: {status}")
    except Exception as e:
        print(f"Model validation skipped: {e}")

    yield
    print("Shutting down LLM Council API...")


app = FastAPI(title="LLM Council", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== Request Models ==========


class MessageRequest(BaseModel):
    content: str
    council_id: str = "personal"
    panel_override: Optional[List[Dict[str, str]]] = None
    force_direct: bool = False
    execution_mode: str = "full"  # "chat" | "ranked" | "full"


class RouteRequest(BaseModel):
    question: str


class CreateConversationRequest(BaseModel):
    council_id: str = "personal"


class ModelsConfigRequest(BaseModel):
    models: List[Dict[str, str]]
    chairman: str
    title_model: Optional[str] = None
    deliberation: Optional[Dict[str, Any]] = None


class CouncilConfigRequest(BaseModel):
    name: str
    description: str = ""
    type: str = "persona"
    default_model: str = ""
    personas: List[Dict[str, str]] = []
    rubric: List[Dict[str, Any]] = []
    models: List[str] = []


class CreateCouncilRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    type: str = "persona"
    default_model: str = ""
    personas: List[Dict[str, str]] = []
    rubric: List[Dict[str, Any]] = []
    models: List[str] = []


# ========== Config Endpoints ==========


@app.get("/api/config")
async def get_config():
    config = load_config()
    return config


@app.put("/api/config")
async def update_config(request: ModelsConfigRequest):
    try:
        data = request.model_dump(exclude_none=True)
        saved = save_models_config(data)
        reload_runtime_config()
        return {"status": "ok", "config": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")


# ========== Council Config Endpoints ==========


@app.post("/api/councils")
async def create_council(request: CreateCouncilRequest):
    council_id = request.id
    if not re.match(r'^[a-z0-9][a-z0-9-]*$', council_id):
        raise HTTPException(status_code=400, detail="Council ID must be lowercase alphanumeric with hyphens")

    existing = get_council(council_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Council '{council_id}' already exists")

    try:
        data = request.model_dump(exclude={"id"})
        if not data.get("models"):
            data.pop("models", None)
        if not data.get("default_model"):
            data.pop("default_model", None)
        saved = save_council_config(council_id, data)
        reload_runtime_config()
        return {"status": "ok", "council": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/councils/{council_id}")
async def update_council(council_id: str, request: CouncilConfigRequest):
    existing = get_council(council_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Council '{council_id}' not found")

    try:
        data = request.model_dump()
        if not data.get("models"):
            data.pop("models", None)
        if not data.get("default_model"):
            data.pop("default_model", None)
        saved = save_council_config(council_id, data)
        reload_runtime_config()
        return {"status": "ok", "council": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/councils/{council_id}")
async def delete_council_endpoint(council_id: str):
    try:
        delete_council_config(council_id)
        reload_runtime_config()
        return {"status": "ok"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Council '{council_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== Council Endpoints ==========


@app.get("/api/councils")
async def list_councils():
    return get_councils_summary()


@app.get("/api/councils/{council_id}")
async def get_council_detail(council_id: str):
    council = get_council(council_id)
    if not council:
        raise HTTPException(status_code=404, detail=f"Council {council_id} not found")
    return council


# ========== Advisor & Routing Endpoints ==========


@app.get("/api/councils/{council_id}/advisors")
async def list_advisors(council_id: str):
    """List the full advisor roster for a council."""
    council = get_council(council_id)
    if not council:
        raise HTTPException(status_code=404, detail=f"Council {council_id} not found")
    advisors = get_advisors(council_id)
    routing = get_routing_config(council_id)
    return {
        "council_id": council_id,
        "advisors": advisors,
        "routing": routing,
        "models": get_council_models(),
    }


@app.post("/api/councils/{council_id}/route")
async def route_question(council_id: str, request: RouteRequest):
    """Route a question to the most relevant advisors."""
    council = get_council(council_id)
    if not council:
        raise HTTPException(status_code=404, detail=f"Council {council_id} not found")

    panel, _routing_usage = await stage0_route_question(request.question, council_id)
    advisors = get_advisors(council_id)
    routing = get_routing_config(council_id)

    return {
        "panel": panel,
        "available_advisors": [
            {"id": a["id"], "name": a["name"], "role": a.get("role", ""), "tags": a.get("tags", [])}
            for a in advisors
        ],
        "routing": routing,
        "models": get_council_models(),
    }


# ========== Conversation Endpoints ==========


@app.get("/api/conversations")
async def list_conversations(council_id: Optional[str] = None):
    return storage.list_conversations(council_id)


@app.post("/api/conversations")
async def create_conversation(request: CreateConversationRequest = CreateConversationRequest()):
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id, request.council_id)
    return conversation


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    conversation = storage.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, council_id: str = "personal"):
    success = storage.soft_delete_conversation(conversation_id, council_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


# ========== Streaming Message Endpoint ==========


async def _drain_queue(queue: asyncio.Queue):
    """Drain all pending events from a queue, yielding SSE lines."""
    while not queue.empty():
        try:
            event_data = queue.get_nowait()
            yield f"data: {event_data}\n\n"
        except asyncio.QueueEmpty:
            break


@app.post("/api/conversations/{conversation_id}/message/stream-tokens")
async def send_message_stream_tokens(conversation_id: str, request: MessageRequest):
    council_id = request.council_id
    content = request.content
    panel_override = request.panel_override
    force_direct = request.force_direct

    conversation = storage.get_conversation(conversation_id, council_id)
    if not conversation:
        conversation = storage.create_conversation(conversation_id, council_id)

    storage.add_user_message(conversation_id, content, council_id)

    execution_mode = request.execution_mode  # "chat" | "ranked" | "full"

    async def event_stream():
        panel = panel_override  # May be None
        conversation_history = conversation.get("messages", [])
        usage_tracker = UsageAggregator()
        event_queue = asyncio.Queue()

        # Emit execution mode so frontend knows what stages to expect
        yield f"data: {json.dumps({'type': 'execution_mode', 'mode': execution_mode})}\n\n"

        def queue_event(event_type, data):
            """Put an event onto the queue for SSE emission."""
            event_queue.put_nowait(json.dumps({"type": event_type, **data}))

        try:
            # Force direct: skip classification entirely, go straight to chairman
            if force_direct:
                classification = {"type": "direct", "reasoning": "User requested chairman-only response"}
                yield f"data: {json.dumps({'type': 'classification_complete', **classification})}\n\n"
                msg_type = "direct"
            else:
                # Stage 0: Classify (with history for follow-up detection)
                yield f"data: {json.dumps({'type': 'classification_start'})}\n\n"

                classification = await classify_message(
                    content,
                    conversation_history=conversation_history,
                )
                if classification.get("usage"):
                    usage_tracker.record("classification", get_title_model(), classification["usage"])
                    yield f"data: {json.dumps({'type': 'usage_update', 'stage': 'classification', 'usage': usage_tracker.get_stage_summary('classification'), 'running_total': usage_tracker.get_total()})}\n\n"
                yield f"data: {json.dumps({'type': 'classification_complete', **classification})}\n\n"

                msg_type = classification.get("type", "deliberation")

            if msg_type in ("factual", "chat", "followup", "direct"):
                yield f"data: {json.dumps({'type': 'direct_start'})}\n\n"

                result = await chairman_direct_response(
                    content,
                    tool_result=None,
                    conversation_history=conversation_history,
                )
                if result.get("usage"):
                    usage_tracker.record("direct", result.get("model", ""), result["usage"])
                    yield f"data: {json.dumps({'type': 'usage_update', 'stage': 'direct', 'usage': usage_tracker.get_stage_summary('direct'), 'running_total': usage_tracker.get_total()})}\n\n"
                response_text = result.get("response", "")

                yield f"data: {json.dumps({'type': 'stage3_complete', 'model': result.get('model', ''), 'response': response_text})}\n\n"

                final_usage = usage_tracker.get_breakdown()
                storage.add_assistant_message(
                    conversation_id,
                    stage1=[],
                    stage2=[],
                    stage3={"model": result.get("model", ""), "response": response_text},
                    council_id=council_id,
                    usage=final_usage,
                )

                title_usage = await _generate_title(conversation_id, council_id, content, response_text)
                if title_usage:
                    usage_tracker.record("title", get_title_model(), title_usage)
                final_usage = usage_tracker.get_breakdown()
                yield f"data: {json.dumps({'type': 'done', 'usage': final_usage})}\n\n"
                return

            # Route question if no panel override provided
            if panel is None:
                yield f"data: {json.dumps({'type': 'routing_start'})}\n\n"

                panel, routing_usage = await stage0_route_question(content, council_id)
                if routing_usage:
                    usage_tracker.record("routing", get_title_model(), routing_usage)
                    yield f"data: {json.dumps({'type': 'usage_update', 'stage': 'routing', 'usage': usage_tracker.get_stage_summary('routing'), 'running_total': usage_tracker.get_total()})}\n\n"

                yield f"data: {json.dumps({'type': 'routing_complete', 'panel': panel})}\n\n"

            yield f"data: {json.dumps({'type': 'panel_confirmed', 'panel': panel})}\n\n"

            # Track advisor selection for leaderboard
            if panel:
                try:
                    record_advisor_selection(council_id, panel)
                except Exception:
                    pass  # non-critical

            # ===== Web Search (if question benefits from current info) =====
            search_context_str = None
            if detect_search_intent(content):
                yield f"data: {json.dumps({'type': 'search_start', 'query': content})}\n\n"
                try:
                    search_result = await search(content, max_results=3, fetch_content=True)
                    if search_result.results:
                        search_context_str = search_result.to_prompt_context()
                        yield f"data: {json.dumps({'type': 'search_complete', 'provider': search_result.provider, 'results_count': len(search_result.results), 'results': [{'title': r.title, 'url': r.url, 'snippet': r.snippet[:200]} for r in search_result.results]})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'search_complete', 'provider': '', 'results_count': 0, 'results': []})}\n\n"
                except Exception as e:
                    print(f"Search error: {e}")
                    yield f"data: {json.dumps({'type': 'search_complete', 'provider': 'error', 'results_count': 0, 'results': []})}\n\n"

            # ===== Stage 1: Collect responses with progressive events =====
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"

            stage1_completed = [0]

            def stage1_on_event(event_type, data):
                if event_type == "stage1_init":
                    queue_event("stage1_init", data)
                elif event_type == "stage1_model_complete":
                    stage1_completed[0] += 1
                    queue_event("stage1_progress", {
                        "completed": stage1_completed[0],
                        "total": data.get("total", len(panel) if panel else 0),
                        "model": data.get("model", ""),
                        "role": data.get("role", ""),
                        "member_id": data.get("member_id", ""),
                    })
                    queue_event("stage1_model_complete", data)
                elif event_type in ("stage1_token", "stage1_thinking"):
                    queue_event(event_type, data)

            # Run stage1 as a task so we can drain events in parallel
            stage1_task = asyncio.create_task(
                stage1_collect_responses_streaming(
                    content,
                    on_event=stage1_on_event,
                    council_id=council_id,
                    panel=panel,
                    conversation_history=conversation_history,
                    search_context=search_context_str,
                )
            )

            # Drain events while stage1 runs
            while not stage1_task.done():
                try:
                    event_data = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    continue

            # Drain remaining events
            async for line in _drain_queue(event_queue):
                yield line

            stage1_results = stage1_task.result()

            yield f"data: {json.dumps({'type': 'stage1_complete', 'results': [{'model': r['model'], 'role': r.get('role', ''), 'member_id': r.get('member_id', '')} for r in stage1_results]})}\n\n"

            # Record stage1 usage
            for result in stage1_results:
                if result.get("usage"):
                    usage_tracker.record("stage1", result["model"], result["usage"], member_id=result.get("member_id", ""))
            yield f"data: {json.dumps({'type': 'usage_update', 'stage': 'stage1', 'usage': usage_tracker.get_stage_summary('stage1'), 'running_total': usage_tracker.get_total()})}\n\n"

            if not stage1_results:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No advisors responded in Stage 1'})}\n\n"
                return

            # Chat mode: stop after Stage 1 (responses only, no ranking/synthesis)
            if execution_mode == "chat":
                # Use best response as the "final" answer (first model's response)
                best = stage1_results[0]
                stage3_result = {"model": best["model"], "response": best.get("response", ""), "type": "chat_only"}
                yield f"data: {json.dumps({'type': 'stage3_complete', 'model': best['model'], 'response': best.get('response', '')})}\n\n"

                final_usage = usage_tracker.get_breakdown()
                storage.add_assistant_message(
                    conversation_id,
                    stage1=stage1_results,
                    stage2=[],
                    stage3=stage3_result,
                    council_id=council_id,
                    panel=panel,
                    usage=final_usage,
                )

                title_usage = await _generate_title(conversation_id, council_id, content, best.get("response", ""))
                if title_usage:
                    usage_tracker.record("title", get_title_model(), title_usage)
                final_usage = usage_tracker.get_breakdown()
                yield f"data: {json.dumps({'type': 'done', 'usage': final_usage})}\n\n"
                return

            # ===== Stage 2: Rankings with progressive events =====
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"

            stage2_completed = [0]

            def stage2_on_event(event_type, data):
                if event_type == "stage2_init":
                    queue_event("stage2_init", data)
                elif event_type == "stage2_model_complete":
                    stage2_completed[0] += 1
                    queue_event("stage2_progress", {
                        "completed": stage2_completed[0],
                        "total": data.get("total", len(panel) if panel else 0),
                        "model": data.get("model", ""),
                        "role": data.get("role", ""),
                        "member_id": data.get("member_id", ""),
                    })
                    queue_event("stage2_model_complete", data)
                elif event_type in ("stage2_token", "stage2_thinking", "round_start", "round_complete"):
                    queue_event(event_type, data)

            stage2_task = asyncio.create_task(
                stage2_collect_rankings_streaming(
                    content, stage1_results,
                    on_event=stage2_on_event,
                    council_id=council_id,
                    panel=panel,
                )
            )

            while not stage2_task.done():
                try:
                    event_data = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    continue

            async for line in _drain_queue(event_queue):
                yield line

            stage2_results, label_to_model, deliberation_meta = stage2_task.result()

            if deliberation_meta:
                yield f"data: {json.dumps({'type': 'analysis', **deliberation_meta})}\n\n"

            yield f"data: {json.dumps({'type': 'stage2_complete'})}\n\n"

            # Record stage2 usage
            flat_stage2 = []
            if isinstance(stage2_results, list):
                for item in stage2_results:
                    if isinstance(item, list):
                        flat_stage2.extend(item)
                    elif isinstance(item, dict):
                        flat_stage2.append(item)

            for result in flat_stage2:
                if isinstance(result, dict) and result.get("usage"):
                    usage_tracker.record("stage2", result["model"], result["usage"], member_id=result.get("member_id", ""))
            yield f"data: {json.dumps({'type': 'usage_update', 'stage': 'stage2', 'usage': usage_tracker.get_stage_summary('stage2'), 'running_total': usage_tracker.get_total()})}\n\n"

            # Ranked mode: stop after Stage 2 (responses + rankings, no synthesis)
            if execution_mode == "ranked":
                # Use top-ranked model's response as the "final" answer
                agg = deliberation_meta.get("aggregate_rankings", []) if deliberation_meta else []
                if agg:
                    top_model = agg[0].get("model", "")
                    top_response = next((r.get("response", "") for r in stage1_results if r["model"] == top_model), "")
                else:
                    top_model = stage1_results[0]["model"]
                    top_response = stage1_results[0].get("response", "")

                stage3_result = {"model": top_model, "response": top_response, "type": "ranked_only"}
                yield f"data: {json.dumps({'type': 'stage3_complete', 'model': top_model, 'response': top_response})}\n\n"

                final_usage = usage_tracker.get_breakdown()
                storage.add_assistant_message(
                    conversation_id,
                    stage1=stage1_results,
                    stage2=flat_stage2,
                    stage3=stage3_result,
                    council_id=council_id,
                    analysis=deliberation_meta,
                    panel=panel,
                    usage=final_usage,
                )

                try:
                    if agg:
                        model_scores = {}
                        for item in agg:
                            m = item.get("model", "")
                            if m:
                                model_scores[m] = 1.0 / item.get("average_rank", 999)
                        winner = agg[0].get("model", "") if agg else ""
                        record_deliberation_result(council_id, model_scores, winner, panel=panel)
                except Exception:
                    pass

                title_usage = await _generate_title(conversation_id, council_id, content, top_response)
                if title_usage:
                    usage_tracker.record("title", get_title_model(), title_usage)
                final_usage = usage_tracker.get_breakdown()
                yield f"data: {json.dumps({'type': 'done', 'usage': final_usage})}\n\n"
                return

            # ===== Stage 3: Chairman synthesis with streaming =====
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"

            def stage3_on_event(event_type, data):
                queue_event(event_type, data)

            stage3_task = asyncio.create_task(
                stage3_synthesize_streaming(
                    content, stage1_results, flat_stage2,
                    on_event=stage3_on_event,
                    council_id=council_id,
                    analysis=deliberation_meta,
                    conversation_history=conversation_history,
                )
            )

            while not stage3_task.done():
                try:
                    event_data = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    continue

            async for line in _drain_queue(event_queue):
                yield line

            stage3_result = stage3_task.result()

            # Emit stage3_complete if not already emitted by the on_event callback
            yield f"data: {json.dumps({'type': 'stage3_complete', 'model': stage3_result.get('model', ''), 'response': stage3_result.get('response', '')})}\n\n"

            # Record stage3 usage
            if stage3_result.get("usage"):
                usage_tracker.record("stage3", stage3_result.get("model", ""), stage3_result["usage"])
            yield f"data: {json.dumps({'type': 'usage_update', 'stage': 'stage3', 'usage': usage_tracker.get_stage_summary('stage3'), 'running_total': usage_tracker.get_total()})}\n\n"

            # Save to storage with panel metadata
            final_usage = usage_tracker.get_breakdown()
            storage.add_assistant_message(
                conversation_id,
                stage1=stage1_results,
                stage2=flat_stage2,
                stage3=stage3_result,
                council_id=council_id,
                analysis=deliberation_meta,
                panel=panel,
                usage=final_usage,
            )

            # Record deliberation results for leaderboard
            try:
                agg = deliberation_meta.get("aggregate_rankings", []) if deliberation_meta else []
                if agg:
                    model_scores = {}
                    for item in agg:
                        m = item.get("model", "")
                        if m:
                            model_scores[m] = 1.0 / item.get("average_rank", 999)
                    winner = agg[0].get("model", "") if agg else ""
                    record_deliberation_result(council_id, model_scores, winner, panel=panel)
            except Exception:
                pass  # non-critical

            title_usage = await _generate_title(conversation_id, council_id, content, stage3_result.get("response", ""))
            if title_usage:
                usage_tracker.record("title", get_title_model(), title_usage)
            final_usage = usage_tracker.get_breakdown()
            yield f"data: {json.dumps({'type': 'done', 'usage': final_usage})}\n\n"

        except Exception as e:
            import traceback
            print(f"Error in stream: {traceback.format_exc()}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _generate_title(conversation_id: str, council_id: str, user_query: str, response: str, event_stream_yield=None) -> dict:
    """Generate a title for the conversation using the title model. Returns usage dict."""
    try:
        from .openrouter import query_model
        title_model = get_title_model()
        messages = [
            {"role": "user", "content": f"Generate a concise title (max 6 words) for this conversation:\n\nUser: {user_query[:200]}\n\nAssistant: {response[:200]}\n\nRespond with ONLY the title, no quotes or extra text."}
        ]
        result = await query_model(title_model, messages, timeout=30, temperature=0.3)
        if result and result.get("content"):
            title = result["content"].strip().strip('"').strip("'")[:80]
            storage.update_conversation_title(conversation_id, title, council_id)
            return result.get("usage", {})
    except Exception as e:
        print(f"Title generation failed: {e}")
    return {}


# ========== Temperature Config Endpoint ==========


@app.get("/api/config/temperatures")
async def get_temperatures():
    return get_stage_temperatures()


# ========== Search Endpoints ==========


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
    provider: Optional[str] = None
    fetch_content: bool = False


@app.get("/api/config/search")
async def get_search_config_endpoint():
    """Get search configuration (available providers, etc.)."""
    return get_search_config()


@app.post("/api/search")
async def search_endpoint(request: SearchRequest):
    """Perform a manual web search."""
    result = await search(
        request.query,
        max_results=request.max_results,
        provider=request.provider,
        fetch_content=request.fetch_content,
    )
    return {
        "query": result.query,
        "provider": result.provider,
        "results": [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "has_content": bool(r.content)}
            for r in result.results
        ],
    }


# ========== Import/Export Config Endpoints ==========


@app.get("/api/config/export")
async def export_config():
    """Export all configuration (models + councils) as a single JSON bundle."""
    try:
        models_config = load_config()
        councils_data = {}
        councils_summary = get_councils_summary()
        for c in councils_summary:
            council = get_council(c["id"])
            if council:
                councils_data[c["id"]] = council
        return {
            "version": 1,
            "models": models_config,
            "councils": councils_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


class ImportConfigRequest(BaseModel):
    version: int = 1
    models: Optional[Dict[str, Any]] = None
    councils: Optional[Dict[str, Any]] = None


@app.post("/api/config/import")
async def import_config(request: ImportConfigRequest):
    """Import configuration from a JSON bundle. Merges with existing config."""
    results = {"models_updated": False, "councils_updated": [], "errors": []}
    try:
        if request.models:
            models_data = request.models
            save_data = {
                "models": models_data.get("models", []),
                "chairman": models_data.get("chairman", ""),
            }
            if models_data.get("title_model"):
                save_data["title_model"] = models_data["title_model"]
            if models_data.get("deliberation"):
                save_data["deliberation"] = models_data["deliberation"]
            save_models_config(save_data)
            results["models_updated"] = True

        if request.councils:
            for council_id, council_data in request.councils.items():
                try:
                    data = {k: v for k, v in council_data.items() if k != "id"}
                    save_council_config(council_id, data)
                    results["councils_updated"].append(council_id)
                except Exception as e:
                    results["errors"].append(f"{council_id}: {str(e)}")

        reload_config()
        reload_runtime_config()
        return {"status": "ok", **results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


# ========== Leaderboard Endpoints ==========


@app.get("/api/leaderboard")
async def get_leaderboards():
    return get_all_leaderboards()


@app.get("/api/leaderboard/advisors")
async def get_advisor_leaderboards_all():
    return get_all_advisor_leaderboards()


@app.get("/api/leaderboard/{council_id}")
async def get_leaderboard(council_id: str):
    return get_council_leaderboard(council_id)



@app.get("/api/leaderboard/{council_id}/advisors")
async def get_advisor_leaderboard_endpoint(council_id: str):
    return get_advisor_leaderboard(council_id)


# ========== Health Check ==========


@app.get("/api/health")
async def health_check():
    config = load_config()
    councils = load_councils()
    return {
        "status": "ok",
        "models": [m["id"] for m in config.get("models", [])],
        "chairman": config.get("chairman"),
        "councils": list(councils.keys()),
    }
