"""Configuration for the LLM Council."""

import os
import json
import msvcrt
from typing import Dict, List, Optional, Tuple, TypedDict
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

# Chairman model - synthesizes final response (fallback when no chairman set)
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"

MODEL_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "model_registry.json")
MODEL_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "model_state.json")


class ModelRegistryEntry(TypedDict):
    id: str
    notes: Optional[str]
    expensive: Optional[bool]
    capabilities: Dict[str, object]


def _ensure_unique_models(models: List[str], source_name: str) -> None:
    seen = set()
    duplicates = set()
    for model in models:
        if model in seen:
            duplicates.add(model)
        else:
            seen.add(model)
    if duplicates:
        dup_str = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate model(s) {dup_str} defined in {source_name}")


def load_model_registry() -> List[ModelRegistryEntry]:
    """Load the model registry (static metadata)."""
    if not os.path.exists(MODEL_REGISTRY_PATH):
        return []

    with open(MODEL_REGISTRY_PATH, "r", encoding="utf-8") as handle:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            raw = json.load(handle)
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    if isinstance(raw, dict):
        entries = raw.get("models", [])
    else:
        entries = raw

    if not isinstance(entries, list):
        raise ValueError("model_registry.json must contain a list or {\"models\": [...]} structure")

    models: List[ModelRegistryEntry] = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id", "").strip()
        if not model_id:
            raise ValueError("model_registry.json entry missing 'id'")
        if model_id in seen:
            raise ValueError(f"Duplicate model '{model_id}' found in model_registry.json")
        seen.add(model_id)
        capabilities = entry.get("capabilities") or {}
        if not isinstance(capabilities, dict):
            capabilities = {}
        models.append({
            "id": model_id,
            "notes": entry.get("notes"),
            "expensive": entry.get("expensive"),
            "capabilities": capabilities,
        })

    return models


def save_model_registry(entries: List[ModelRegistryEntry]) -> None:
    """Persist the model registry."""
    payload = {"models": entries}
    with open(MODEL_REGISTRY_PATH, "r+", encoding="utf-8") as handle:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            handle.truncate(0)
            handle.seek(0)
            json.dump(payload, handle, indent=2)
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def get_browse_capable_models() -> set:
    """Return set of model IDs that have web search capability."""
    registry_entries = load_model_registry()
    browse_capable = set()
    for entry in registry_entries:
        model_id = entry.get("id")
        if not isinstance(model_id, str):
            continue
        capabilities = entry.get("capabilities") or {}
        if isinstance(capabilities, dict):
            can_browse = capabilities.get("can_browse") or capabilities.get("web_search")
            if can_browse:
                browse_capable.add(model_id)
    return browse_capable


def get_coding_capable_models() -> set:
    """Return set of model IDs that have coding capability."""
    registry_entries = load_model_registry()
    coding_capable = set()
    for entry in registry_entries:
        model_id = entry.get("id")
        if not isinstance(model_id, str):
            continue
        capabilities = entry.get("capabilities") or {}
        if isinstance(capabilities, dict):
            if capabilities.get("coding"):
                coding_capable.add(model_id)
    return coding_capable


def get_all_models():
    """Return all available models: base council list plus any additions."""
    _ensure_unique_models(COUNCIL_MODELS, "COUNCIL_MODELS")

    registry_entries = load_model_registry()
    all_models = set(COUNCIL_MODELS)
    for entry in registry_entries:
        model_name = entry.get("id")
        if isinstance(model_name, str):
            all_models.add(model_name)
    return all_models


def _normalize_legacy_state_entry(value: object) -> Tuple[bool, bool]:
    """Convert legacy enabled/chairman entries to booleans."""
    if isinstance(value, dict):
        enabled = bool(value.get("enabled", True))
        is_chairman = bool(value.get("is_chairman") or value.get("is_judge", False))
        return enabled, is_chairman
    return bool(value), False


def _empty_state() -> Dict[str, object]:
    return {"chairman": None, "models": {}}


def load_model_state() -> Dict[str, object]:
    """Load runtime state (chairman + enabled flags)."""
    if not os.path.exists(MODEL_STATE_PATH):
        return _empty_state()

    with open(MODEL_STATE_PATH, "r", encoding="utf-8") as handle:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            raw = json.load(handle)
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    if isinstance(raw, dict) and "models" in raw:
        models_section = raw.get("models", {})
        normalized_models = {}
        if isinstance(models_section, dict):
            for model, meta in models_section.items():
                enabled = True
                if isinstance(meta, dict):
                    enabled = bool(meta.get("enabled", True))
                elif isinstance(meta, bool):
                    enabled = meta
                normalized_models[model] = {"enabled": enabled}
        chairman_value = raw.get("chairman") if isinstance(raw.get("chairman"), str) else None
        return {"chairman": chairman_value, "models": normalized_models}

    if isinstance(raw, dict):
        normalized_models = {}
        chairman_value = None
        for model, value in raw.items():
            enabled, is_chairman = _normalize_legacy_state_entry(value)
            normalized_models[model] = {"enabled": enabled}
            if is_chairman:
                chairman_value = model
        return {"chairman": chairman_value, "models": normalized_models}

    return _empty_state()


def save_model_state(state: Dict[str, object]) -> None:
    """Persist runtime model state."""
    to_save = {
        "chairman": state.get("chairman"),
        "models": {},
    }
    models_section = state.get("models") or {}
    if isinstance(models_section, dict):
        for model, meta in models_section.items():
            enabled = True
            if isinstance(meta, dict):
                enabled = bool(meta.get("enabled", True))
            elif isinstance(meta, bool):
                enabled = meta
            to_save["models"][model] = {"enabled": enabled}
    with open(MODEL_STATE_PATH, "r+", encoding="utf-8") as handle:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            handle.truncate(0)
            handle.seek(0)
            json.dump(to_save, handle, indent=2)
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def get_active_chairman_model(state: Optional[Dict[str, object]] = None) -> str:
    """Return the currently selected chairman model, falling back as needed."""
    if state is None:
        state = load_model_state()
    chairman_value = state.get("chairman")
    if isinstance(chairman_value, str) and chairman_value in get_all_models():
        return chairman_value

    return CHAIRMAN_MODEL


def get_council_models_active():
    """Return enabled models from the persisted model state."""
    all_models = get_all_models()
    state = load_model_state()
    models_section = state.get("models") if isinstance(state, dict) else {}
    active = []
    for model in all_models:
        enabled = True
        if isinstance(models_section, dict):
            entry = models_section.get(model)
            if isinstance(entry, dict):
                enabled = bool(entry.get("enabled", True))
            elif isinstance(entry, bool):
                enabled = entry
        if enabled:
            active.append(model)
    return active
