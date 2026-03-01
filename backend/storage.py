"""JSON-based storage for conversations with per-council directories."""

import json
import os
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

BASE_DATA_DIR = Path(__file__).parent.parent / "data" / "conversations"


def _council_dir(council_id: str = "personal") -> Path:
    return BASE_DATA_DIR / council_id


def ensure_data_dir(council_id: str = "personal"):
    _council_dir(council_id).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str, council_id: str = "personal") -> str:
    return str(_council_dir(council_id) / f"{conversation_id}.json")


def create_conversation(conversation_id: str, council_id: str = "personal") -> Dict[str, Any]:
    ensure_data_dir(council_id)
    conversation = {
        "id": conversation_id,
        "council_id": council_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": f"Conversation {conversation_id[:8]}",
        "messages": [],
    }
    path = get_conversation_path(conversation_id, council_id)
    with open(path, "w") as f:
        json.dump(conversation, f, indent=2)
    return conversation


def get_conversation(conversation_id: str, council_id: str = "personal") -> Optional[Dict[str, Any]]:
    path = get_conversation_path(conversation_id, council_id)
    if not os.path.exists(path):
        for cdir in BASE_DATA_DIR.iterdir():
            if cdir.is_dir():
                alt_path = cdir / f"{conversation_id}.json"
                if alt_path.exists():
                    with open(alt_path, "r") as f:
                        return json.load(f)
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_conversation(conversation: Dict[str, Any]):
    council_id = conversation.get("council_id", "personal")
    ensure_data_dir(council_id)
    path = get_conversation_path(conversation["id"], council_id)
    with open(path, "w") as f:
        json.dump(conversation, f, indent=2, default=str)


def update_conversation(conversation_id: str, conversation: Dict[str, Any]):
    save_conversation(conversation)


def delete_conversation(conversation_id: str, council_id: str = "personal") -> bool:
    try:
        path = get_conversation_path(conversation_id, council_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
    except Exception:
        return False


def soft_delete_conversation(conversation_id: str, council_id: str = "personal") -> bool:
    try:
        conversation = get_conversation(conversation_id, council_id)
        if not conversation:
            return False
        conversation["deleted"] = True
        conversation["deleted_at"] = time.time()
        save_conversation(conversation)
        return True
    except Exception as e:
        print(f"Error soft deleting {conversation_id}: {e}")
        return False


def list_conversations(council_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conversations = []

    if council_id:
        dirs = [_council_dir(council_id)]
    else:
        BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        dirs = [d for d in BASE_DATA_DIR.iterdir() if d.is_dir()]

    for data_dir in dirs:
        if not data_dir.exists():
            continue
        for filename in os.listdir(data_dir):
            if not filename.endswith(".json"):
                continue
            path = data_dir / filename
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                created_at = data.get("created_at", "")
                if isinstance(created_at, (int, float)):
                    created_at = datetime.fromtimestamp(created_at).isoformat()
                conversations.append({
                    "id": data["id"],
                    "council_id": data.get("council_id", data_dir.name),
                    "created_at": created_at,
                    "title": data.get("title", "New Conversation"),
                    "message_count": len(data.get("messages", [])),
                    "deleted": data.get("deleted", False),
                })
            except Exception as e:
                print(f"Error reading {filename}: {e}")

    def sort_key(conv):
        ca = conv["created_at"]
        if isinstance(ca, str):
            try:
                return datetime.fromisoformat(ca.replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0
        return float(ca) if ca else 0

    conversations.sort(key=sort_key, reverse=True)
    return conversations


def add_user_message(conversation_id: str, content: str, council_id: str = "personal"):
    conversation = get_conversation(conversation_id, council_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    conversation["messages"].append({"role": "user", "content": content})
    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    council_id: str = "personal",
    analysis: Optional[Dict[str, Any]] = None,
    panel: Optional[List[Dict[str, str]]] = None,
    usage: Optional[Dict[str, Any]] = None,
):
    conversation = get_conversation(conversation_id, council_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    message = {
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
    }
    if analysis:
        message["analysis"] = analysis
    if panel:
        message["panel"] = panel
    if usage:
        message["usage"] = usage
    conversation["messages"].append(message)
    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str, council_id: str = "personal"):
    conversation = get_conversation(conversation_id, council_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    conversation["title"] = title
    save_conversation(conversation)
