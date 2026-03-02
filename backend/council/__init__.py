"""3-stage LLM Council orchestration with dynamic advisor routing.

This package provides the full deliberation pipeline:
- Stage 0: Message classification and advisor routing
- Stage 1: Collect individual responses from council members
- Stage 2: Multi-round peer rankings with rubric scoring
- Stage 3: Chairman synthesis of final answer
"""

from .routing import classify_message, stage0_route_question, chairman_direct_response
from .stage1 import stage1_collect_responses_streaming
from .stage2 import stage2_collect_rankings_streaming
from .stage3 import stage3_synthesize_streaming
from .ranking import calculate_aggregate_rankings
from .utils import UsageAggregator, TokenTracker

__all__ = [
    "classify_message",
    "stage0_route_question",
    "chairman_direct_response",
    "stage1_collect_responses_streaming",
    "stage2_collect_rankings_streaming",
    "stage3_synthesize_streaming",
    "calculate_aggregate_rankings",
    "UsageAggregator",
    "TokenTracker",
]
