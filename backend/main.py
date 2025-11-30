"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid
import json
import asyncio
import sys

from . import storage
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings
from .config import (
    OPENROUTER_API_KEY,
    COUNCIL_MODELS,
    get_all_models,
    load_model_registry,
    save_model_registry,
    load_model_state,
    save_model_state,
    get_active_chairman_model,
    ModelRegistryEntry,
)

if OPENROUTER_API_KEY:
    print("OPENROUTER_API_KEY found")
else:
    print("OPENROUTER_API_KEY not found; quitting")
    sys.exit(1)

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    web_search: bool = False


class ModelToggleRequest(BaseModel):
    """Request to toggle a model's enabled state."""
    model: str
    enabled: bool


class ModelChairmanRequest(BaseModel):
    """Request to set the current chairman model."""
    model: str


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/models")
async def get_models():
    """Get all models with their enabled state and notes."""
    registry_entries = load_model_registry()
    model_state = load_model_state()
    active_chairman = get_active_chairman_model(model_state)
    notes = {}
    browse_capable_models = set()
    for entry in registry_entries:
        model_id = entry.get("id")
        if not isinstance(model_id, str):
            continue
        if entry.get("notes"):
            notes[model_id] = entry["notes"]
        capabilities = entry.get("capabilities") or {}
        if isinstance(capabilities, dict):
            can_browse = capabilities.get("can_browse")
            if can_browse is None:
                can_browse = capabilities.get("web_search")
            if can_browse:
                browse_capable_models.add(model_id)
    models_state = model_state.get("models") if isinstance(model_state, dict) else {}

    all_models = get_all_models()

    result = []
    for model in sorted(all_models):
        is_base = model in COUNCIL_MODELS

        enabled = True
        if isinstance(models_state, dict):
            state_entry = models_state.get(model)
            if isinstance(state_entry, dict):
                enabled = bool(state_entry.get("enabled", True))
            elif isinstance(state_entry, bool):
                enabled = state_entry

        entry = {
            "model": model,
            "enabled": enabled,
            "is_base": is_base,
            "can_browse": model in browse_capable_models,
            "is_chairman": model == active_chairman,
        }
        if model in notes:
            entry["notes"] = notes[model]

        result.append(entry)

    return result


@app.post("/api/models/toggle")
async def toggle_model(request: ModelToggleRequest):
    """Toggle a model's enabled state."""
    state = load_model_state()
    models_state = state.get("models")
    if not isinstance(models_state, dict):
        models_state = {}
        state["models"] = models_state
    entry = models_state.get(request.model, {"enabled": True})
    if not isinstance(entry, dict):
        entry = {"enabled": bool(entry)}
    entry["enabled"] = request.enabled
    models_state[request.model] = entry
    save_model_state(state)
    return {"success": True}


@app.post("/api/models/chairman")
async def set_chairman_model(request: ModelChairmanRequest):
    """Set which model acts as chairman."""
    model = request.model
    if model not in get_all_models():
        raise HTTPException(status_code=400, detail="Unknown model")

    state = load_model_state()
    state["chairman"] = model
    models_state = state.get("models")
    if not isinstance(models_state, dict):
        models_state = {}
        state["models"] = models_state
    if model not in models_state:
        models_state[model] = {"enabled": True}
    save_model_state(state)
    return {"success": True}


@app.post("/api/models/add")
async def add_model(request: Dict[str, str]):
    """Add a new model to the available list."""
    model = request.get("model", "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name required")

    registry_entries = load_model_registry()
    if any(entry.get("id") == model for entry in registry_entries):
        raise HTTPException(status_code=400, detail="Model already exists in model_registry.json")

    can_browse_value = request.get("can_browse")
    if not isinstance(can_browse_value, bool):
        legacy_value = request.get("has_news")
        can_browse_value = legacy_value if isinstance(legacy_value, bool) else False

    entry: ModelRegistryEntry = {
        "id": model,
        "notes": None,
        "expensive": None,
        "capabilities": {},
    }
    notes_value = request.get("notes")
    if isinstance(notes_value, str) and notes_value.strip():
        entry["notes"] = notes_value.strip()
    if can_browse_value:
        entry["capabilities"] = {"can_browse": True}

    registry_entries.append(entry)
    save_model_registry(registry_entries)

    state = load_model_state()
    models_state = state.get("models")
    if not isinstance(models_state, dict):
        models_state = {}
        state["models"] = models_state
    entry_state = models_state.get(model, {"enabled": True})
    if not isinstance(entry_state, dict):
        entry_state = {"enabled": bool(entry_state)}
    entry_state["enabled"] = True
    models_state[model] = entry_state
    save_model_state(state)

    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
