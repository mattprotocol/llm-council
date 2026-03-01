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
)
from .config import reload_runtime_config
from .leaderboard import get_council_leaderboard, get_all_leaderboards, get_advisor_leaderboard, get_all_advisor_leaderboards, record_deliberation_result, record_advisor_selection


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


# ========== Advisor & Routing Endpoints (NEW) ==========


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

    panel = await stage0_route_question(request.question, council_id)
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

    async def event_stream():
        panel = panel_override  # May be None
        conversation_history = conversation.get("messages", [])

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
                yield f"data: {json.dumps({'type': 'classification_complete', **classification})}\n\n"

                msg_type = classification.get("type", "deliberation")

            if msg_type in ("factual", "chat", "followup", "direct"):
                yield f"data: {json.dumps({'type': 'direct_start'})}\n\n"

                result = await chairman_direct_response(
                    content,
                    tool_result=None,
                    conversation_history=conversation_history,
                )
                response_text = result.get("response", "")

                yield f"data: {json.dumps({'type': 'stage3_complete', 'model': result.get('model', ''), 'response': response_text})}\n\n"

                storage.add_assistant_message(
                    conversation_id,
                    stage1=[],
                    stage2=[],
                    stage3={"model": result.get("model", ""), "response": response_text},
                    council_id=council_id,
                )

                await _generate_title(conversation_id, council_id, content, response_text)
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # Route question if no panel override provided
            if panel is None:
                yield f"data: {json.dumps({'type': 'routing_start'})}\n\n"

                panel = await stage0_route_question(content, council_id)

                yield f"data: {json.dumps({'type': 'routing_complete', 'panel': panel})}\n\n"

            yield f"data: {json.dumps({'type': 'panel_confirmed', 'panel': panel})}\n\n"

            # Track advisor selection for leaderboard
            if panel:
                try:
                    record_advisor_selection(council_id, panel)
                except Exception:
                    pass  # non-critical

            # Stage 1: Collect responses from panel (with conversation history)
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"

            stage1_results = await stage1_collect_responses_streaming(
                content,
                on_event=lambda t, d: None,
                council_id=council_id,
                panel=panel,
                conversation_history=conversation_history,
            )

            for result in stage1_results:
                yield f"data: {json.dumps({'type': 'stage1_model_complete', 'model': result['model'], 'role': result.get('role', ''), 'member_id': result.get('member_id', ''), 'response': result['response']})}\n\n"

            yield f"data: {json.dumps({'type': 'stage1_complete', 'results': [{'model': r['model'], 'role': r.get('role', ''), 'member_id': r.get('member_id', '')} for r in stage1_results]})}\n\n"

            if not stage1_results:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No advisors responded in Stage 1'})}\n\n"
                return

            # Stage 2: Rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"

            stage2_results, label_to_model, deliberation_meta = await stage2_collect_rankings_streaming(
                content, stage1_results,
                on_event=lambda t, d: None,
                council_id=council_id,
                panel=panel,
            )

            for result in (stage2_results if isinstance(stage2_results, list) else [stage2_results]):
                if isinstance(result, list):
                    for r in result:
                        yield f"data: {json.dumps({'type': 'stage2_model_complete', **{k: v for k, v in r.items() if k != 'parsed_ranking'}})}\n\n"
                elif isinstance(result, dict):
                    yield f"data: {json.dumps({'type': 'stage2_model_complete', **{k: v for k, v in result.items() if k != 'parsed_ranking'}})}\n\n"

            if deliberation_meta:
                yield f"data: {json.dumps({'type': 'analysis', **deliberation_meta})}\n\n"

            yield f"data: {json.dumps({'type': 'stage2_complete'})}\n\n"

            # Stage 3: Chairman synthesis
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"

            flat_stage2 = []
            if isinstance(stage2_results, list):
                for item in stage2_results:
                    if isinstance(item, list):
                        flat_stage2.extend(item)
                    elif isinstance(item, dict):
                        flat_stage2.append(item)

            stage3_result = await stage3_synthesize_streaming(
                content, stage1_results, flat_stage2,
                on_event=lambda t, d: None,
                council_id=council_id,
                analysis=deliberation_meta,
                conversation_history=conversation_history,
            )

            yield f"data: {json.dumps({'type': 'stage3_complete', 'model': stage3_result.get('model', ''), 'response': stage3_result.get('response', '')})}\n\n"

            # Save to storage with panel metadata
            storage.add_assistant_message(
                conversation_id,
                stage1=stage1_results,
                stage2=flat_stage2,
                stage3=stage3_result,
                council_id=council_id,
                analysis=deliberation_meta,
                panel=panel,
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
            await _generate_title(conversation_id, council_id, content, stage3_result.get("response", ""))
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            import traceback
            print(f"Error in stream: {traceback.format_exc()}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _generate_title(conversation_id: str, council_id: str, user_query: str, response: str, event_stream_yield=None):
    """Generate a title for the conversation using the title model."""
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
    except Exception as e:
        print(f"Title generation failed: {e}")


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
