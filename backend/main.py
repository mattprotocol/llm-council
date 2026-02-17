"""FastAPI backend for multi-council LLM deliberation."""

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
)
from .leaderboard import get_council_leaderboard, get_all_leaderboards


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifespan events."""
    print("Starting LLM Council API...")
    config = load_config()
    councils = load_councils()
    models = get_council_models()
    print(f"Loaded {len(councils)} councils: {list(councils.keys())}")
    print(f"Council models: {models}")

    # Validate models on OpenRouter
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


# ========== Models ==========


class MessageRequest(BaseModel):
    content: str
    council_id: str = "personal"


class CreateConversationRequest(BaseModel):
    council_id: str = "personal"


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

    # Load or create conversation
    conversation = storage.get_conversation(conversation_id, council_id)
    if not conversation:
        conversation = storage.create_conversation(conversation_id, council_id)

    # Add user message
    storage.add_user_message(conversation_id, content, council_id)

    async def event_stream():
        try:
            # Stage 0: Classify
            yield f"data: {json.dumps({'type': 'classification_start'})}\n\n"

            classification = await classify_message(content)
            yield f"data: {json.dumps({'type': 'classification_complete', **classification})}\n\n"

            msg_type = classification.get("type", "deliberation")

            if msg_type in ("factual", "chat"):
                # Direct chairman response
                yield f"data: {json.dumps({'type': 'direct_start'})}\n\n"

                conversation_history = conversation.get("messages", [])
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

                # Generate title
                await _generate_title(conversation_id, council_id, content, response_text, event_stream_yield=None)

                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # Full deliberation
            # Stage 1: Collect responses with persona injection
            stage1_results = []

            def on_stage1_event(event_type, data):
                nonlocal stage1_results
                if event_type == "stage1_model_complete":
                    stage1_results.append({
                        "model": data.get("model", ""),
                        "response": data.get("response", ""),
                    })

            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"

            stage1_results = await stage1_collect_responses_streaming(
                content,
                on_event=lambda t, d: None,  # We'll capture via the yielded events
                council_id=council_id,
            )

            for result in stage1_results:
                yield f"data: {json.dumps({'type': 'stage1_model_complete', 'model': result['model'], 'response': result['response']})}\n\n"

            yield f"data: {json.dumps({'type': 'stage1_complete', 'results': [{'model': r['model']} for r in stage1_results]})}\n\n"

            if not stage1_results:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No models responded in Stage 1'})}\n\n"
                return

            # Stage 2: Rankings with rubric scoring
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"

            stage2_results, label_to_model, deliberation_meta = await stage2_collect_rankings_streaming(
                content, stage1_results,
                on_event=lambda t, d: None,
                council_id=council_id,
            )

            for result in (stage2_results if isinstance(stage2_results, list) else [stage2_results]):
                if isinstance(result, list):
                    for r in result:
                        yield f"data: {json.dumps({'type': 'stage2_model_complete', **{k: v for k, v in r.items() if k != 'parsed_ranking'}})}\n\n"
                elif isinstance(result, dict):
                    yield f"data: {json.dumps({'type': 'stage2_model_complete', **{k: v for k, v in result.items() if k != 'parsed_ranking'}})}\n\n"

            # Include analysis metadata (conflicts, minority opinions)
            if deliberation_meta:
                yield f"data: {json.dumps({'type': 'analysis', **deliberation_meta})}\n\n"

            yield f"data: {json.dumps({'type': 'stage2_complete'})}\n\n"

            # Stage 3: Chairman synthesis
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"

            # Flatten stage2 results for synthesis
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
            )

            yield f"data: {json.dumps({'type': 'stage3_complete', 'model': stage3_result.get('model', ''), 'response': stage3_result.get('response', '')})}\n\n"

            # Save to storage
            storage.add_assistant_message(
                conversation_id,
                stage1=stage1_results,
                stage2=flat_stage2,
                stage3=stage3_result,
                council_id=council_id,
                analysis=deliberation_meta,
            )

            # Generate title
            await _generate_title(conversation_id, council_id, content, stage3_result.get("response", ""), event_stream_yield=None)

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


@app.get("/api/leaderboard/{council_id}")
async def get_leaderboard(council_id: str):
    return get_council_leaderboard(council_id)


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
