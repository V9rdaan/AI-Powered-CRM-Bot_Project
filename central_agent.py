"""
Central Agent: Acts as the primary coordinator.
Responsibilities:
- Receives user message
- Checks CRM/Postgres for lead stage and profile
- Populates state with retrieved data
- Resets retry counter
- Passes updated state to LangGraph pipeline
"""


from database.postgres_client import fetch_crm_data
from models.user_profile import UserProfile
from models.lead import Lead

class CentralAgent:
    def handle(self, state: dict) -> dict:
        user_id = state.get("user_id")
        user_msg = state.get("user_message")

        print(f"[CentralAgent] Received message from {user_id}: {user_msg}")

        crm = fetch_crm_data(user_id)

        # Extract data with models
        lead_data = crm.get("lead_data") if crm else {}
        profile_data = crm.get("profile_data") if crm else {}

        lead = Lead(**lead_data) if lead_data else Lead(stage=1)
        profile = UserProfile(**profile_data) if profile_data else UserProfile(user_id=user_id)

        state["lead_stage"] = f"Stage {lead.stage}"
        state["profile_data"] = profile.dict()
        state["retry_count"] = 0

        print(f"[CentralAgent] Updated state → lead_stage: {state['lead_stage']}")
        print(f"[CentralAgent] Profile data keys: {list(profile.dict().keys())}")

        return state