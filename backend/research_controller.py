"""
Self-Improving Research Controller

This module implements a recursive research agent that:
1. Reads context from Graphiti memory before processing queries
2. Uses a state machine approach (Think → Research/Build/Answer)
3. Writes learned knowledge back to memory
4. Can dynamically build new tools via mcp-dev-team

The controller maintains a research state and iterates until the query is answered
or the maximum number of rounds is reached.
"""

import json
import asyncio
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ResearchState:
    """State object for the research loop."""
    user_query: str
    current_knowledge: List[Dict[str, Any]] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    current_round: int = 0
    max_rounds: int = 50
    status: str = "WORKING"  # WORKING, FINISHED, ERROR
    final_answer: Optional[str] = None
    lessons_learned: List[Dict[str, Any]] = field(default_factory=list)
    

CONTROLLER_SYSTEM_PROMPT = """# Role
You are the **Recursive Research Controller**, the primary entry point for all user queries. You are an autonomous agent capable of self-improvement and intelligent routing.

# Capabilities
1. **Graphiti Memory:** You possess a semantic knowledge graph. You do not need to research facts you have already learned.
2. **Dynamic Tooling:** You have access to a suite of MCP tools.
3. **Tool Fabrication:** If you lack a tool required to answer a query, you can **build it yourself** using the `mcp-dev-team` meta-tool.
4. **Council Escalation:** For complex ethical, philosophical, or multi-perspective questions, you can escalate to the LLM Council for deliberation.

# Current Environment
**User Query:** "{user_query}"

**Graphiti Context (Known Facts):**
{current_context}

**Currently Registered Tools:**
{available_tools}

**Action History:**
{action_history}

# Decision Logic (The Loop)
Analyze the User Query and your Current Context. Follow this priority order strictly:

1. **COMPLETE:** If the "Graphiti Context" contains sufficient information to fully answer the User Query, output the Final Answer.
2. **DIRECT ANSWER:** If the query is a simple greeting, chitchat, or factual question you can answer from general knowledge, provide a direct response.
3. **USE EXISTING:** If information is missing, check "Currently Registered Tools". If a relevant tool exists, use it.
4. **BUILD NEW:** If information is missing AND no existing tool can retrieve it, you must **BUILD** a new tool.
   * Heuristic: Break the missing capability down into the smallest possible functional unit.
   * Action: Call `mcp-dev-team` to build a new tool.
5. **ESCALATE:** If the query is:
   - A complex ethical or philosophical question requiring multiple perspectives
   - A creative task requiring deliberation (e.g., naming, brainstorming)
   - A subjective opinion question with no factual answer
   - Beyond your capabilities after exhausting tools
   Set status to "ESCALATE" to hand off to the LLM Council.
6. **CORRECT:** If a previous tool execution failed (see context), analyze the error and retry with fixed parameters.

# Output Format
You must respond with a SINGLE valid JSON object. Do not include markdown formatting or prose outside the JSON.

**Schema:**
{{
  "thought_process": "Brief reasoning about what is known vs. unknown and why you are choosing this action.",
  "status": "WORKING" | "FINISHED" | "ESCALATE",
  "action": {{
    "name": "tool_name_to_call or null if FINISHED/ESCALATE",
    "parameters": {{ ... }}
  }},
  "missing_information": ["list of what is still unknown"],
  "final_answer": "Only populate if status is FINISHED. Otherwise null.",
  "escalation_reason": "Only populate if status is ESCALATE. Explains why council deliberation is needed.",
  "lessons_learned": ["Any insights about the query, process, or data that should be saved to memory"]
}}

# Important Constraints
* **Do not hallucinate data.** If it is not in "Graphiti Context", you do not know it.
* **Tool Building:** When building a tool, be highly specific in the requirements parameter.
* **Iterative Approach:** One loop = One specific action.
* **Knowledge Recording:** Always identify lessons learned that should be saved for future queries.
"""


class SelfImprovingResearchController:
    """
    Controller for self-improving research that:
    - Retrieves context from Graphiti before processing
    - Runs a state machine loop to answer queries
    - Records learned knowledge back to memory
    """
    
    def __init__(self, memory_service=None, mcp_registry=None, llm_query_func=None):
        """
        Initialize the controller.
        
        Args:
            memory_service: The Graphiti memory service
            mcp_registry: The MCP tool registry
            llm_query_func: Function to query an LLM
        """
        self.memory_service = memory_service
        self.mcp_registry = mcp_registry
        self.llm_query_func = llm_query_func
        
    async def get_memory_context(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve relevant context from Graphiti memory."""
        if not self.memory_service:
            return []
        
        try:
            # Search memory for relevant context (use search_memories with 's')
            results = await self.memory_service.search_memories(query, limit=limit)
            return results if results else []
        except Exception as e:
            print(f"[Research Controller] Memory search error: {e}")
            return []
    
    async def get_available_tools(self) -> List[str]:
        """Get list of available MCP tools."""
        if not self.mcp_registry:
            return []
        
        try:
            tools = self.mcp_registry.all_tools
            return [f"{t.server_name}.{t.name}" for t in tools.values()] if tools else []
        except Exception as e:
            print(f"[Research Controller] Tool registry error: {e}")
            return []
    
    async def save_lesson_to_memory(self, lesson: Dict[str, Any], query: str) -> bool:
        """Save a learned lesson to Graphiti memory."""
        if not self.memory_service:
            return False
        
        try:
            episode_content = f"Lesson learned while researching '{query[:50]}...': {lesson.get('content', str(lesson))}"
            await self.memory_service.add_episode(
                content=episode_content,
                metadata={
                    "type": "lesson_learned",
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    **lesson
                }
            )
            return True
        except Exception as e:
            print(f"[Research Controller] Failed to save lesson: {e}")
            return False
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool and return results."""
        if not self.mcp_registry:
            return {"success": False, "error": "MCP registry not available"}
        
        try:
            result = await self.mcp_registry.call_tool(tool_name, parameters)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_llm_decision(self, state: ResearchState) -> Dict[str, Any]:
        """Get the LLM's next action decision based on current state."""
        if not self.llm_query_func:
            return {"status": "ERROR", "error": "LLM query function not available"}
        
        # Format context for prompt
        context_str = json.dumps(state.current_knowledge, indent=2) if state.current_knowledge else "No relevant context found in memory."
        tools_str = "\n".join(f"- {t}" for t in state.available_tools) if state.available_tools else "No tools available."
        history_str = json.dumps(state.action_history[-5:], indent=2) if state.action_history else "No actions taken yet."
        
        prompt = CONTROLLER_SYSTEM_PROMPT.format(
            user_query=state.user_query,
            current_context=context_str,
            available_tools=tools_str,
            action_history=history_str
        )
        
        try:
            response = await self.llm_query_func(
                [{"role": "system", "content": prompt}, {"role": "user", "content": "Decide on the next action."}],
                timeout=60
            )
            
            if response and response.get('content'):
                content = response['content']
                # Try to parse JSON from response
                try:
                    if '```json' in content:
                        content = content.split('```json')[1].split('```')[0]
                    elif '```' in content:
                        content = content.split('```')[1].split('```')[0]
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"status": "ERROR", "error": "Could not parse LLM response as JSON", "raw": content}
            
            return {"status": "ERROR", "error": "Empty LLM response"}
            
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    async def run_research_loop(self, query: str, on_event=None) -> Dict[str, Any]:
        """
        Run the main research loop.
        
        Args:
            query: The user's query to research
            on_event: Optional callback for streaming events
            
        Returns:
            Final result with answer and metadata
        """
        # Initialize state
        state = ResearchState(user_query=query)
        
        # Get initial context from memory
        if on_event:
            on_event("memory_search_start", {"query": query})
        
        state.current_knowledge = await self.get_memory_context(query)
        state.available_tools = await self.get_available_tools()
        
        if on_event:
            on_event("memory_search_complete", {
                "facts_found": len(state.current_knowledge),
                "tools_available": len(state.available_tools)
            })
        
        print(f"[Research Controller] Starting loop for: {query[:50]}...")
        print(f"[Research Controller] Found {len(state.current_knowledge)} relevant facts in memory")
        print(f"[Research Controller] {len(state.available_tools)} tools available")
        
        # === SEMANTIC INTENT CLASSIFICATION ===
        # Use LLM to determine the best routing for this query
        if on_event:
            on_event("intent_classification_start", {"query": query})
        
        intent_result = await classify_query_intent(
            query=query,
            available_tools=state.available_tools,
            llm_query_func=self.llm_query_func,
            timeout=15
        )
        
        intent = intent_result.get("intent", "COUNCIL_DELIBERATION")
        reasoning = intent_result.get("reasoning", "")
        tool_hints = intent_result.get("tool_hints", [])
        
        print(f"[Research Controller] Intent: {intent} - {reasoning}")
        
        if on_event:
            on_event("intent_classification_complete", {
                "intent": intent,
                "reasoning": reasoning,
                "tool_hints": tool_hints
            })
        
        # Handle immediate escalation to council
        if intent == "COUNCIL_DELIBERATION":
            return {
                "success": False,
                "status": "ESCALATE",
                "answer": None,
                "rounds_taken": 0,
                "facts_used": len(state.current_knowledge),
                "lessons_learned": [],
                "action_summary": [],
                "escalation_reason": reasoning or "Query benefits from multi-perspective council deliberation"
            }
        
        # Handle direct response for simple queries
        if intent == "DIRECT_RESPONSE":
            # Let the LLM provide a quick direct answer
            try:
                direct_response = await self.llm_query_func(
                    [{"role": "user", "content": query}],
                    timeout=30
                )
                if direct_response and direct_response.get("content"):
                    return {
                        "success": True,
                        "status": "FINISHED",
                        "answer": direct_response["content"],
                        "rounds_taken": 1,
                        "facts_used": len(state.current_knowledge),
                        "lessons_learned": [],
                        "action_summary": [{"round": 1, "tool": None, "thought": "Direct response to simple query"}]
                    }
            except Exception as e:
                print(f"[Research Controller] Direct response error: {e}")
            # Fall through to research loop if direct response fails
        
        # Main loop
        while state.current_round < state.max_rounds and state.status == "WORKING":
            state.current_round += 1
            
            if on_event:
                on_event("round_start", {"round": state.current_round})
            
            print(f"[Research Controller] Round {state.current_round}/{state.max_rounds}")
            
            # Get LLM decision
            decision = await self.get_llm_decision(state)
            
            if decision.get("status") == "ERROR":
                print(f"[Research Controller] Error: {decision.get('error')}")
                state.status = "ERROR"
                break
            
            # Record action in history
            action_record = {
                "round": state.current_round,
                "thought": decision.get("thought_process", ""),
                "action": decision.get("action"),
                "timestamp": datetime.now().isoformat()
            }
            state.action_history.append(action_record)
            
            # Update missing information
            if decision.get("missing_information"):
                state.missing_information = decision["missing_information"]
            
            # Check if finished
            if decision.get("status") == "FINISHED":
                state.status = "FINISHED"
                state.final_answer = decision.get("final_answer")
                state.lessons_learned = decision.get("lessons_learned", [])
                break
            
            # Check if escalating to council
            if decision.get("status") == "ESCALATE":
                state.status = "ESCALATE"
                state.escalation_reason = decision.get("escalation_reason", "Complex query requires council deliberation")
                state.lessons_learned = decision.get("lessons_learned", [])
                if on_event:
                    on_event("escalate_to_council", {"reason": state.escalation_reason})
                print(f"[Research Controller] Escalating to council: {state.escalation_reason}")
                break
            
            # Execute action
            action = decision.get("action", {})
            if action and action.get("name"):
                tool_name = action["name"]
                parameters = action.get("parameters", {})
                
                if on_event:
                    on_event("tool_execution_start", {"tool": tool_name, "parameters": parameters})
                
                print(f"[Research Controller] Executing tool: {tool_name}")
                result = await self.execute_tool(tool_name, parameters)
                
                # Add result to action record
                action_record["result"] = result
                
                if on_event:
                    on_event("tool_execution_complete", {"tool": tool_name, "success": result.get("success")})
                
                # If tool succeeded, update knowledge
                if result.get("success"):
                    state.current_knowledge.append({
                        "source": f"tool:{tool_name}",
                        "data": result.get("result"),
                        "round": state.current_round
                    })
        
        # Save lessons to memory
        if state.lessons_learned:
            print(f"[Research Controller] Saving {len(state.lessons_learned)} lessons to memory")
            for lesson in state.lessons_learned:
                if isinstance(lesson, str):
                    lesson = {"content": lesson}
                await self.save_lesson_to_memory(lesson, query)
        
        # Return result
        result = {
            "success": state.status == "FINISHED",
            "status": state.status,
            "answer": state.final_answer,
            "rounds_taken": state.current_round,
            "facts_used": len(state.current_knowledge),
            "lessons_learned": state.lessons_learned,
            "action_summary": [
                {"round": a["round"], "tool": a.get("action", {}).get("name"), "thought": a.get("thought", "")[:100]}
                for a in state.action_history
            ]
        }
        
        # Add escalation info if applicable
        if state.status == "ESCALATE":
            result["escalation_reason"] = getattr(state, 'escalation_reason', 'Unknown')
        
        return result


# Knowledge categories for memory storage
KNOWLEDGE_CATEGORIES = {
    "fact": "A verified piece of information",
    "process": "A step-by-step procedure or workflow",
    "lesson": "An insight learned from experience",
    "preference": "A user preference or configuration",
    "entity": "Information about a person, place, or thing",
    "relationship": "A connection between entities",
    "error_correction": "A correction to previously incorrect information"
}


async def augment_query_with_memory(
    query: str,
    memory_service,
    max_facts: int = 5
) -> Dict[str, Any]:
    """
    Augment a user query with relevant context from memory.
    
    This is a lightweight pre-processing step that retrieves relevant
    facts before the main council deliberation.
    
    Args:
        query: The user's query
        memory_service: The Graphiti memory service
        max_facts: Maximum number of facts to retrieve
        
    Returns:
        Dict with query, context, and metadata
    """
    context = []
    
    if memory_service:
        try:
            # Use search_memories (with 's') - the correct method name
            results = await memory_service.search_memories(query, limit=max_facts)
            if results:
                context = results
        except Exception as e:
            print(f"[Memory Augment] Error searching memory: {e}")
    
    return {
        "original_query": query,
        "context": context,
        "context_count": len(context),
        "augmented": len(context) > 0
    }


async def record_interaction_to_memory(
    query: str,
    response: str,
    memory_service,
    category: str = "fact",
    extract_entities: bool = True
) -> bool:
    """
    Record an interaction to memory for future retrieval.
    
    Args:
        query: The user's query
        response: The assistant's response
        memory_service: The Graphiti memory service
        category: Type of knowledge being stored
        extract_entities: Whether to extract and store entities
        
    Returns:
        True if successfully recorded
    """
    if not memory_service:
        return False
    
    try:
        # Create episode content
        episode_content = f"Q: {query}\nA: {response}"
        
        await memory_service.add_episode(
            content=episode_content,
            metadata={
                "type": "conversation",
                "category": category,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return True
    except Exception as e:
        print(f"[Memory Record] Error recording interaction: {e}")
        return False


# Factory function to create controller
def create_research_controller(memory_service=None, mcp_registry=None, llm_query_func=None):
    """Create a configured research controller instance."""
    return SelfImprovingResearchController(
        memory_service=memory_service,
        mcp_registry=mcp_registry,
        llm_query_func=llm_query_func
    )


# Prompt for semantic intent classification
INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier. Analyze the user's query and determine what type of processing is needed.

**User Query:** "{query}"

**Available Tools:** {tools_summary}

Classify the intent into ONE of these categories:
1. **RESEARCH_CONTROLLER** - Use when:
   - Query requires tool usage (weather, location, data lookup, etc.)
   - Query asks to create/generate artifacts (images, files, tools, etc.)
   - Query requires external data or API calls
   - Query needs iterative research or information gathering
   - Complex multi-step tasks requiring tool orchestration

2. **COUNCIL_DELIBERATION** - Use when:
   - Query is philosophical, ethical, or requires multiple perspectives
   - Query is subjective and benefits from diverse viewpoints
   - Query is creative writing/brainstorming without tool needs
   - Complex reasoning that doesn't require external data

3. **DIRECT_RESPONSE** - Use when:
   - Simple greeting or chitchat
   - Basic factual question answerable from general knowledge
   - Simple follow-up or clarification
   - Conversational exchange not requiring tools or deep deliberation

Respond with ONLY a JSON object:
{{
  "intent": "RESEARCH_CONTROLLER" | "COUNCIL_DELIBERATION" | "DIRECT_RESPONSE",
  "reasoning": "Brief explanation of why this classification was chosen",
  "tool_hints": ["optional list of tool names that might be relevant"]
}}"""


async def classify_query_intent(
    query: str,
    available_tools: List[str],
    llm_query_func,
    timeout: int = 15
) -> Dict[str, Any]:
    """
    Use LLM to semantically classify query intent.
    
    Args:
        query: The user's query
        available_tools: List of available tool names
        llm_query_func: Async function to query the LLM
        timeout: Maximum time for classification
        
    Returns:
        Dict with intent classification and reasoning
    """
    if not llm_query_func:
        # Fallback to keyword matching if no LLM available
        return {
            "intent": "COUNCIL_DELIBERATION",
            "reasoning": "No LLM available for semantic classification",
            "tool_hints": []
        }
    
    # Summarize tools for prompt
    if available_tools:
        tools_summary = ", ".join(available_tools[:30])  # Limit to avoid huge prompts
        if len(available_tools) > 30:
            tools_summary += f" (and {len(available_tools) - 30} more)"
    else:
        tools_summary = "No tools currently available"
    
    prompt = INTENT_CLASSIFICATION_PROMPT.format(
        query=query,
        tools_summary=tools_summary
    )
    
    try:
        response = await asyncio.wait_for(
            llm_query_func(
                [{"role": "user", "content": prompt}],
                timeout=timeout
            ),
            timeout=timeout + 5
        )
        
        if response and response.get('content'):
            content = response['content']
            # Parse JSON from response
            try:
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                result = json.loads(content.strip())
                
                # Validate intent
                valid_intents = ["RESEARCH_CONTROLLER", "COUNCIL_DELIBERATION", "DIRECT_RESPONSE"]
                if result.get("intent") not in valid_intents:
                    result["intent"] = "COUNCIL_DELIBERATION"  # Safe default
                
                return result
            except json.JSONDecodeError:
                print(f"[Intent Classifier] Failed to parse JSON: {content[:200]}")
                # Try to extract intent from malformed response using regex
                intent_match = re.search(r'"intent"\s*:\s*"(RESEARCH_CONTROLLER|COUNCIL_DELIBERATION|DIRECT_RESPONSE)"', content)
                if intent_match:
                    extracted_intent = intent_match.group(1)
                    print(f"[Intent Classifier] Extracted intent via regex: {extracted_intent}")
                    return {
                        "intent": extracted_intent,
                        "reasoning": "Extracted from malformed JSON",
                        "tool_hints": []
                    }
                
                # Fallback: check for keywords to infer intent
                content_lower = content.lower()
                if any(kw in content_lower for kw in ["research_controller", "tool", "create", "generate", "image", "build"]):
                    print("[Intent Classifier] Inferring RESEARCH_CONTROLLER from keywords")
                    return {
                        "intent": "RESEARCH_CONTROLLER",
                        "reasoning": "Inferred from keywords in malformed response",
                        "tool_hints": []
                    }
                elif any(kw in content_lower for kw in ["direct", "simple", "greeting", "chitchat"]):
                    print("[Intent Classifier] Inferring DIRECT_RESPONSE from keywords")
                    return {
                        "intent": "DIRECT_RESPONSE",
                        "reasoning": "Inferred from keywords in malformed response",
                        "tool_hints": []
                    }
                
                return {
                    "intent": "COUNCIL_DELIBERATION",
                    "reasoning": "Failed to parse LLM response",
                    "tool_hints": []
                }
        
        return {
            "intent": "COUNCIL_DELIBERATION",
            "reasoning": "Empty LLM response",
            "tool_hints": []
        }
        
    except asyncio.TimeoutError:
        print("[Intent Classifier] Timeout during classification")
        return {
            "intent": "COUNCIL_DELIBERATION",
            "reasoning": "Classification timed out",
            "tool_hints": []
        }
    except Exception as e:
        print(f"[Intent Classifier] Error: {e}")
        return {
            "intent": "COUNCIL_DELIBERATION",
            "reasoning": f"Classification error: {str(e)}",
            "tool_hints": []
        }


def should_use_research_controller(query: str) -> bool:
    """
    DEPRECATED: Use classify_query_intent() for semantic classification.
    
    This function is kept for backward compatibility but will be replaced
    by the async semantic classifier.
    
    Args:
        query: The user's query
        
    Returns:
        True if the query should use the research controller (simple heuristic)
    """
    # Simple heuristic fallback - check for obvious tool-related patterns
    query_lower = query.lower()
    
    tool_indicators = [
        "weather", "temperature", "forecast",
        "location", "where am i", "my location",
        "time", "date", "what day",
        "create an image", "generate an image", "draw", "make a picture",
        "build a tool", "create a tool", "make a tool",
        "search for", "look up", "find out",
        "research", "investigate"
    ]
    
    for indicator in tool_indicators:
        if indicator in query_lower:
            return True
    
    return False
