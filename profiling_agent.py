"""
Extracts user information (e.g., name, preferences) and stores it in Redis and PostgreSQL (CRM unified).
"""

from models.user_profile import UserProfile
from models.lead import Lead
from utils.info_extractor import extract_info
from database.redis_client import set_user_profile
from database.postgres_client import upsert_crm_data, fetch_crm_data

class ProfilingAgent:
    def handle(self, user_input, user_profile_dict, profile_key):
        # Ensure compatibility: If already dict, keep it, else convert to dict
        if isinstance(user_profile_dict, dict):
            base_profile = user_profile_dict
        else:
            base_profile = user_profile_dict.dict()  # just in case it's UserProfile

        # Extract info using the updated function signature
        extracted = extract_info(base_profile, user_input)
        print(f"[ProfilingAgent] Extracted info: {extracted}")

        # Track changes for all fields and keep previous values
        updated_profile = base_profile.copy()
        for key, new_value in extracted.items():
            old_value = base_profile.get(key)
            if old_value is not None and old_value != new_value:
                prev_key = f"previous_{key}"
                # If already have a previous value, don't overwrite it
                if prev_key not in updated_profile:
                    updated_profile[prev_key] = old_value
            updated_profile[key] = new_value

        # Ensure user_id is set
        if not updated_profile.get("user_id"):
            updated_profile["user_id"] = profile_key

        # Do NOT save to Redis here; let main.py handle it after enforcing lead_stage

        # Fetch or create lead data
        existing = fetch_crm_data(updated_profile["user_id"])
        lead = Lead(**existing["lead_data"]) if existing and "lead_data" in existing else Lead(stage=1)

        # Upsert unified CRM data
        upsert_crm_data(updated_profile["user_id"], updated_profile, lead.dict())

        return updated_profile  # Return as dict, not .dict()