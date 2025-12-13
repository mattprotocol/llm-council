"""
Multi-tool orchestration for complex queries requiring multiple tool calls.

Uses a planning phase to decompose queries into steps, then executes tools
sequentially, passing results between steps.
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
import uuid

from .mcp.registry import get_mcp_registry
from .lmstudio import query_model
from .config_loader import get_chairman_model


async def needs_multi_tool_orchestration(user_query: str) -> bool:
    """
    Determine if a query requires multi-tool orchestration.
    
    Patterns that suggest multi-step execution:
    - Time-relative queries (yesterday, last week, tomorrow)
    - Queries combining location + time + data (weather, events)
    - Complex calculations requiring multiple inputs
    """
    query_lower = user_query.lower()
    
    # Time-relative patterns that need date calculation + another tool
    time_relative_patterns = [
        ("yesterday", ["weather", "news", "events", "happened"]),
        ("last week", ["weather", "news", "events", "happened"]),
        ("tomorrow", ["weather", "forecast"]),
        ("next week", ["weather", "forecast"]),
        ("last month", ["weather", "news", "events"]),
    ]
    
    for time_pattern, context_words in time_relative_patterns:
        if time_pattern in query_lower:
            if any(word in query_lower for word in context_words):
                return True
    
    # Queries that need location + time + data
    multi_context_patterns = [
        ("weather", "here"),  # Need location + current time + weather
        ("weather", "now"),
        ("time", "in"),  # Time in different location
    ]
    
    for p1, p2 in multi_context_patterns:
        if p1 in query_lower and p2 in query_lower:
            return True
    
    return False


async def plan_tool_execution(user_query: str, available_tools: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create an execution plan for the query using LLM.
    
    Returns a list of steps, each with:
    - step_number: int
    - description: str
    - tool: str (tool name)
    - depends_on: List[int] (step numbers this depends on)
    - parameters: Dict (parameters for the tool, may include $step_N references)
    """
    chairman = get_chairman_model()
    
    # Format tool list for prompt
    tool_descriptions = []
    for tool_name, tool_info in available_tools.items():
        desc = tool_info.get('description', 'No description')
        params = tool_info.get('inputSchema', {}).get('properties', {})
        param_list = list(params.keys())[:5]  # First 5 params
        tool_descriptions.append(f"- {tool_name}: {desc} (params: {', '.join(param_list)})")
    
    tools_text = "\n".join(tool_descriptions[:15])  # Limit to avoid token overflow
    
    prompt = f"""You are a tool orchestration planner. Given a user query and available tools, create an execution plan.

USER QUERY: "{user_query}"

AVAILABLE TOOLS:
{tools_text}

Create a JSON execution plan with steps to answer the query. Each step should use one tool.

Rules:
1. Use the minimum number of steps necessary
2. Each step can reference results from previous steps using $step_N syntax
3. For date calculations (yesterday, last week), use the calculator or compute directly
4. Include all required parameters for each tool call

Output ONLY valid JSON in this format:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "What this step does",
      "tool": "tool.name",
      "depends_on": [],
      "parameters": {{"param1": "value1"}}
    }},
    {{
      "step_number": 2,
      "description": "Use result from step 1",
      "tool": "another.tool",
      "depends_on": [1],
      "parameters": {{"input": "$step_1.result"}}
    }}
  ]
}}

Example for "what was the weather yesterday?":
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "Get current date and time",
      "tool": "system-date-time.get-current-datetime",
      "depends_on": [],
      "parameters": {{}}
    }},
    {{
      "step_number": 2,
      "description": "Get current location",
      "tool": "system-geo-location.get-geo-location",
      "depends_on": [],
      "parameters": {{}}
    }},
    {{
      "step_number": 3,
      "description": "Get weather for yesterday at current location",
      "tool": "weather.get-weather",
      "depends_on": [1, 2],
      "parameters": {{
        "location": "$step_2.city",
        "date": "YESTERDAY"
      }}
    }}
  ]
}}

Now create the plan for: "{user_query}"
"""

    try:
        response = await query_model(chairman, [{"role": "user", "content": prompt}], timeout=30)
        
        if not response or not response.get('content'):
            return []
        
        content = response['content'].strip()
        
        # Try to extract JSON from response
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()
        
        plan = json.loads(content)
        return plan.get('steps', [])
        
    except Exception as e:
        print(f"[Orchestration] Failed to create plan: {e}")
        return []


def resolve_date_reference(date_str: str, current_date: datetime) -> str:
    """
    Resolve relative date references like YESTERDAY, LAST_WEEK, etc.
    """
    date_upper = date_str.upper().strip()
    
    if date_upper == "YESTERDAY":
        return (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_upper == "TODAY":
        return current_date.strftime("%Y-%m-%d")
    elif date_upper == "TOMORROW":
        return (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_upper == "LAST_WEEK" or date_upper == "LAST WEEK":
        return (current_date - timedelta(weeks=1)).strftime("%Y-%m-%d")
    elif date_upper == "NEXT_WEEK" or date_upper == "NEXT WEEK":
        return (current_date + timedelta(weeks=1)).strftime("%Y-%m-%d")
    
    # Return as-is if not a recognized reference
    return date_str


def resolve_step_references(parameters: Dict, step_results: Dict[int, Any], current_date: datetime = None) -> Dict:
    """
    Resolve $step_N references in parameters to actual values from previous steps.
    Also resolves date references like YESTERDAY.
    """
    resolved = {}
    
    for key, value in parameters.items():
        if isinstance(value, str):
            # Check for step references ($step_N.field)
            if value.startswith("$step_"):
                try:
                    # Parse $step_N.field
                    parts = value[1:].split(".")
                    step_num = int(parts[0].replace("step_", ""))
                    field_path = parts[1:] if len(parts) > 1 else []
                    
                    result = step_results.get(step_num, {})
                    
                    # Navigate to nested field
                    for field in field_path:
                        if isinstance(result, dict):
                            result = result.get(field, result)
                    
                    resolved[key] = result
                except Exception as e:
                    print(f"[Orchestration] Failed to resolve {value}: {e}")
                    resolved[key] = value
            
            # Check for date references
            elif current_date and value.upper() in ["YESTERDAY", "TODAY", "TOMORROW", "LAST_WEEK", "NEXT_WEEK", "LAST WEEK", "NEXT WEEK"]:
                resolved[key] = resolve_date_reference(value, current_date)
            else:
                resolved[key] = value
        else:
            resolved[key] = value
    
    return resolved


async def execute_orchestrated_tools(
    user_query: str,
    on_event: Optional[Callable] = None
) -> Optional[Dict[str, Any]]:
    """
    Execute a multi-tool orchestration workflow.
    
    1. Create execution plan
    2. Execute each step in order
    3. Pass results between steps
    4. Return combined results
    
    Args:
        user_query: The user's question
        on_event: Optional callback for streaming events
        
    Returns:
        Combined results from all tool executions
    """
    registry = get_mcp_registry()
    
    print(f"[Orchestration] Starting multi-tool orchestration for: {user_query[:50]}...")
    
    if on_event:
        on_event("orchestration_start", {"query": user_query})
    
    # Get available tools
    available_tools = registry.all_tools
    if not available_tools:
        print("[Orchestration] No tools available")
        return None
    
    # Create execution plan
    print("[Orchestration] Creating execution plan...")
    plan = await plan_tool_execution(user_query, available_tools)
    
    if not plan:
        print("[Orchestration] Failed to create plan")
        return None
    
    print(f"[Orchestration] Plan created with {len(plan)} steps")
    
    if on_event:
        on_event("orchestration_plan", {"steps": plan})
    
    # Execute each step
    step_results: Dict[int, Any] = {}
    current_date = datetime.now()
    all_outputs = []
    
    for step in plan:
        step_num = step.get('step_number', 0)
        tool_name = step.get('tool', '')
        description = step.get('description', '')
        parameters = step.get('parameters', {})
        
        print(f"[Orchestration] Step {step_num}: {description}")
        print(f"[Orchestration]   Tool: {tool_name}")
        
        # Check dependencies are satisfied
        depends_on = step.get('depends_on', [])
        for dep in depends_on:
            if dep not in step_results:
                print(f"[Orchestration] Missing dependency: step {dep}")
        
        # Resolve step references in parameters
        resolved_params = resolve_step_references(parameters, step_results, current_date)
        print(f"[Orchestration]   Params: {resolved_params}")
        
        # Execute the tool
        call_id = str(uuid.uuid4())[:8]
        
        if on_event:
            on_event("tool_call_start", {
                "tool": tool_name,
                "arguments": resolved_params,
                "call_id": call_id,
                "step": step_num,
                "description": description
            })
        
        try:
            result = await registry.call_tool(tool_name, resolved_params)
            
            # Store result for later steps
            step_results[step_num] = extract_tool_result(result)
            
            if on_event:
                on_event("tool_call_complete", {
                    "tool": tool_name,
                    "result": result,
                    "call_id": call_id,
                    "step": step_num
                })
            
            # Collect output
            if result.get('success'):
                all_outputs.append({
                    "step": step_num,
                    "description": description,
                    "tool": tool_name,
                    "output": step_results[step_num]
                })
            
            print(f"[Orchestration]   Result: success={result.get('success')}")
            
        except Exception as e:
            print(f"[Orchestration]   Failed: {e}")
            step_results[step_num] = {"error": str(e)}
            
            if on_event:
                on_event("tool_call_complete", {
                    "tool": tool_name,
                    "result": {"success": False, "error": str(e)},
                    "call_id": call_id,
                    "step": step_num
                })
    
    # Combine all results
    combined_result = {
        "success": True,
        "tool": "orchestration",
        "server": "orchestration",
        "output": {
            "query": user_query,
            "steps_executed": len(all_outputs),
            "results": all_outputs,
            "final_data": step_results.get(len(plan), step_results.get(max(step_results.keys()) if step_results else 0, {}))
        }
    }
    
    if on_event:
        on_event("orchestration_complete", {
            "query": user_query,
            "steps": len(all_outputs),
            "success": True
        })
    
    print(f"[Orchestration] Complete: {len(all_outputs)} steps executed")
    return combined_result


def extract_tool_result(result: Dict[str, Any]) -> Any:
    """
    Extract the useful data from a tool result for use in subsequent steps.
    """
    if not result.get('success'):
        return result.get('error', 'Failed')
    
    output = result.get('output', {})
    
    # Handle MCP content wrapper
    if isinstance(output, dict) and 'content' in output:
        content = output['content']
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get('text', '')
            try:
                return json.loads(text)
            except:
                return text
    
    return output
