from typing import Optional
from langgraph.graph import StateGraph, END

# Models
from models.user_profile import UserProfile
from models.lead import Lead

# Agents
from agents.central_agent import CentralAgent
from agents.profiling_agent import ProfilingAgent
from agents.dynamic_lead_conversion_agent import DynamicLeadConversionAgent
from agents.prompt_agent import PromptAgent
from agents.reflection_agent import ReflectionAgent

# Define State
from typing import TypedDict

class ChatbotState(TypedDict):
    user_message: str
    user_id: str
    lead_stage: Optional[str]
    profile_data: UserProfile
    response: Optional[str]
    response_history: Optional[list]  # Track response refinement history
    is_valid: Optional[bool]
    retry_count: int
    response_ready: Optional[bool]
    user_message_saved: Optional[bool]  # Track if user message was already saved

# Instantiate Agents
central = CentralAgent()
profiling = ProfilingAgent()
dynamic_lead_conversion = DynamicLeadConversionAgent()
 # greeting = GreetingAgent()
prompt = PromptAgent()
reflection = ReflectionAgent()

# Node Functions
def central_agent(state: ChatbotState) -> ChatbotState:
    if state.get("response_ready"):
        print("[Graph] Final response ready. Exiting.")
        return state
    return state

def profile_agent(state: ChatbotState) -> ChatbotState:
    print("[Graph] Running profiling step.")
    # Run Profiling
    profile_dict = profiling.handle(state["user_message"], state["profile_data"], state["user_id"])
    state["profile_data"] = UserProfile(**profile_dict)
    return state

def dynamic_lead_conversion_agent(state: ChatbotState) -> ChatbotState:
    # Generate response using the dynamic lead conversion agent
    initial_response = dynamic_lead_conversion.handle(
        state["user_message"],
        state["profile_data"].dict(),
        state["user_id"]
    )

    # After progression, fetch the latest stage from the database
    from database.postgres_client import fetch_crm_data
    crm_data = fetch_crm_data(state["user_id"])
    if crm_data and "lead_stage" in crm_data:
        state["lead_stage"] = crm_data["lead_stage"]

    # Initialize response history if not exists
    if not state.get("response_history"):
        state["response_history"] = []

    state["response_history"].append({"agent": "dynamic_lead_conversion", "response": initial_response})
    state["response"] = initial_response
    # Store the original stage response for prompt refinement
    state["original_stage_response"] = initial_response
    print(f"[DynamicLeadConversionAgent] Generated response: {initial_response[:100]}...")
    return state

 # Removed greeting_agent and its logic

def prompt_agent(state: ChatbotState) -> ChatbotState:
    # Final refinement using dynamic prompts and previous response
    state["retry_count"] += 1

    # Dynamically extract stage number from lead_stage string (e.g., "Stage 1", "Stage 2", ...)
    lead_stage_str = state.get("lead_stage", "")
    try:
        if isinstance(lead_stage_str, str) and lead_stage_str.lower().startswith("stage "):
            stage_num = int(lead_stage_str.split(" ")[1])
        else:
            stage_num = 1  # Default to 1 if not found
    except Exception:
        stage_num = 1

    lead = {"stage": stage_num}


    # Pass the current response as previous_response for refinement
    print(f"[PromptAgent] Previous response being refined: {state['response']}")
    refined_response = prompt.handle(
        state["profile_data"].dict(),
        lead,
        state["user_message"],
        previous_response=state["response"],
        user_id=state["user_id"],
        original_stage_response=state.get("original_stage_response", "")
    )

    state["response_history"].append({"agent": "prompt", "response": refined_response})
    state["response"] = refined_response
    print(f"[PromptAgent] Final refined response: {refined_response[:100]}...")
    return state

def reflection_agent(state: ChatbotState) -> ChatbotState:
    # Fetch the current lead goal (stage description) from the DB
    from database.postgres_client import get_stage_config
    lead_stage_str = state.get("lead_stage", "Stage 1")
    try:
        if isinstance(lead_stage_str, str) and lead_stage_str.lower().startswith("stage "):
            stage_num = int(lead_stage_str.split(" ")[1])
        else:
            stage_num = 1
    except Exception:
        stage_num = 1
    
    stage_config = get_stage_config("client_01", stage_num)
    lead_goal = stage_config["description"] if stage_config and "description" in stage_config else ""
    
    # Try enhanced validation first, but with more lenient approach
    try:
        # Use enhanced validation with profiling
        is_valid, validation_details = reflection.validate_with_profiling(
            response=state["response"],
            lead_goal=lead_goal,
            user_input=state["user_message"],
            user_id=state["user_id"],
            profile_data=state["profile_data"].dict() if state.get("profile_data") else {},
            response_history=state.get("response_history", [])
        )
    except Exception as e:
        print(f"[ReflectionAgent] Enhanced validation failed, falling back to basic: {e}")
        # Fallback to legacy validation
        is_valid = reflection.validate(state["response"], lead_goal, state["user_message"])
        validation_details = {"method": "legacy_fallback", "error": str(e)}
    
    state["is_valid"] = is_valid
    
    # If the response is valid, mark the workflow as ready to end
    if state["is_valid"]:
        state["response_ready"] = True
        print(f"[ReflectionAgent] Response validated successfully")
    # If retries exceeded, accept the last response and end
    elif state["retry_count"] >= 3:
        state["response_ready"] = True
        print(f"[ReflectionAgent] Max retries reached, accepting current response")
    else:
        print(f"[ReflectionAgent] Response needs improvement, retry {state['retry_count']}/3")

    return state

# ----------------------
# Build LangGraph
# ----------------------
workflow = StateGraph(ChatbotState)

# Add all nodes
workflow.add_node("central_agent", central_agent)
workflow.add_node("profile_agent", profile_agent)
workflow.add_node("dynamic_lead_conversion_agent", dynamic_lead_conversion_agent)
 # workflow.add_node("greeting_agent", greeting_agent)
workflow.add_node("prompt_agent", prompt_agent)
workflow.add_node("reflection_agent", reflection_agent)

# Entry point
workflow.set_entry_point("central_agent")

# Conditional edge from central_agent to END or profile_agent
workflow.add_conditional_edges(
    "central_agent",
    lambda state: END if state.get("response_ready") else "profile_agent",
    {
        END: END,
        "profile_agent": "profile_agent"
    }
)

workflow.add_conditional_edges(
    "profile_agent",
    lambda state: "dynamic_lead_conversion_agent",  # Always go to dynamic agent
    {
        "dynamic_lead_conversion_agent": "dynamic_lead_conversion_agent"
    }
)

workflow.add_edge("dynamic_lead_conversion_agent", "prompt_agent")
workflow.add_edge("prompt_agent", "reflection_agent")

workflow.add_conditional_edges(
    "reflection_agent",
    lambda state: "prompt_agent" if not state["is_valid"] and state["retry_count"] < 3 else "central_agent",
    {
        "prompt_agent": "prompt_agent",
        "central_agent": "central_agent"
    }
)

 # Compile
graph = workflow.compile()

# Optional visualization
if __name__ == "__main__":
    from langgraph.graph import visualize
    visualize(graph).save("chatbot_workflow.png")