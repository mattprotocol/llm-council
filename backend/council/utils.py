"""Shared utilities for council pipeline: token tracking, usage aggregation, helpers."""

import time
import re
import json
from typing import Dict, Any, Optional


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

def extract_json_from_response(text: str) -> Optional[Dict]:
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
