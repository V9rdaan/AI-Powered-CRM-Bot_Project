"""
Dynamic Lead Conversion Agent - Replaces both lead_qualifier_agent and followup_agent
with client-configurable, goal-driven lead progression system.
"""


import json
from typing import Dict, Any, Optional
from database.postgres_client import get_stage_config, fetch_crm_data, update_user_stage, upsert_crm_data
from database.redis_client import get_conversation_history
from utils.call_llm import call_llm
from config.prompts import DYNAMIC_LEAD_CONVERSION_ANALYSIS_PROMPT
import logging

logger = logging.getLogger(__name__)

class DynamicLeadConversionAgent:
    def _parse_required_fields_from_description(self, description: str) -> list:
        """
        Extract required fields from the stage description using a simple convention.
        For example, if the description contains [name], [email], [phone], etc.,
        or you can define a convention like: 'Required fields: name, email, phone.'
        This function can be improved to match your actual convention.
        """
        import re
        # Example: look for words in brackets or after 'Required fields:'
        bracket_fields = re.findall(r'\[(.*?)\]', description)
        # Also support 'Required fields: name, email, phone.'
        req_match = re.search(r'Required fields:([\w, ]+)', description, re.IGNORECASE)
        comma_fields = []
        if req_match:
            comma_fields = [f.strip() for f in req_match.group(1).split(',') if f.strip()]
        # Combine and deduplicate
        return list(set(bracket_fields + comma_fields))

    def _stage_requirements_met(self, stage_config: dict, user_profile: dict) -> bool:
        """
        Dynamically check required fields for the current stage using the stage description.
        """
        description = stage_config.get('description', '')
        required_fields = self._parse_required_fields_from_description(description)
        if not required_fields:
            return True  # No requirements specified, allow progression
        return all(user_profile.get(f) not in [None, '', 'NULL'] for f in required_fields)
    def __init__(self, client_id: str = "client_01"):
        self.client_id = client_id
    
    def handle(self, user_input: str, user_profile_dict: dict, profile_key: str) -> str:
        """
        Main handler for dynamic lead conversion (progresses only when requirements from stage description are met)
        """
        user_id = user_profile_dict.get("user_id") or profile_key
        # 1. Get current user state from CRM
        crm_data = fetch_crm_data(user_id)
        current_stage = self._extract_current_stage(crm_data)
        # 2. Get stage configuration from lead_table
        stage_config = self._get_stage_config(current_stage)
        if not stage_config:
            logger.error(f"No stage configuration found for stage {current_stage}")
            return "I'm here to help you! Let me understand your needs better. What brings you here today?"
        # 3. Analyze if current stage goal is achieved
        stage_completion = self._analyze_stage_completion(
            user_id=user_id,
            user_input=user_input,
            current_stage=current_stage,
            stage_description=stage_config['description'],
            user_profile=user_profile_dict
        )
        # 4. Handle stage progression logic (progress only if requirements met)
        response = self._handle_stage_progression(
            user_id=user_id,
            user_input=user_input,
            user_profile_dict=user_profile_dict,
            current_stage=current_stage,
            stage_config=stage_config,
            stage_completion=stage_completion
        )
        return response
    
    def _extract_current_stage(self, crm_data: Optional[Dict]) -> int:
        """Extract current lead stage number from CRM data"""
        if not crm_data:
            return 1
        
        lead_stage = crm_data.get('lead_stage', 'Stage 1')
        # Extract number from "Stage X" format
        try:
            if isinstance(lead_stage, str) and lead_stage.startswith('Stage '):
                return int(lead_stage.replace('Stage ', ''))
            elif isinstance(lead_stage, int):
                return lead_stage
            else:
                return 1
        except (ValueError, TypeError):
            return 1
    
    def _get_stage_config(self, stage_number: int) -> Optional[Dict]:
        """Fetch stage configuration from lead_table"""
        return get_stage_config(self.client_id, stage_number)
    
    def _analyze_stage_completion(self, user_id: str, user_input: str, 
                                current_stage: int, stage_description: str, 
                                user_profile: dict) -> Dict[str, Any]:
        """
        Use LLM to analyze if current stage goal has been achieved
        """
        # Get conversation history for context
        conversation_history = get_conversation_history(user_id, limit=20)
        conversation_context = self._format_conversation(conversation_history)

        prompt = DYNAMIC_LEAD_CONVERSION_ANALYSIS_PROMPT.format(
            current_stage=current_stage,
            stage_description=stage_description,
            user_profile=json.dumps(user_profile, indent=2),
            conversation_context=conversation_context,
            user_input=user_input
        )

        try:
            llm_response = call_llm(prompt, temperature=0.3)
            # Try to parse JSON response
            analysis = json.loads(llm_response)
            return analysis
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error in stage completion analysis: {e}")
            # Return safe default
            return {
                "stage_achieved": False,
                "completion_percentage": 25,
                "missing_requirements": ["Continue the conversation to gather more information"],
                "ready_for_progression": False,
                "reasoning": f"Analysis error occurred: {str(e)}"
            }
    
    def _handle_stage_progression(self, user_id: str, user_input: str, 
                                user_profile_dict: dict, current_stage: int,
                                stage_config: Dict, stage_completion: Dict) -> str:
        """
        Handle stage progression logic and generate appropriate response (progress only if requirements met)
        """
        ready = stage_completion.get('ready_for_progression', False)
        required_fields = self._parse_required_fields_from_description(stage_config.get('description', ''))
        missing_fields = [f for f in required_fields if user_profile_dict.get(f) in [None, '', 'NULL']]
        logger.info(f"[DEBUG] Current stage: {current_stage}, Ready: {ready}, Missing fields: {missing_fields}")
        if ready:
            next_stage = current_stage + 1
            next_stage_config = self._get_stage_config(next_stage)
            if next_stage_config:
                success = update_user_stage(user_id, f"Stage {next_stage}", self.client_id)
                logger.info(f"[DEBUG] update_user_stage returned: {success}")
                crm_after = fetch_crm_data(user_id)
                logger.info(f"[DEBUG] CRM lead_stage after update: {crm_after.get('lead_stage') if crm_after else None}")
                if success:
                    response = self._generate_stage_response(
                        user_input=user_input,
                        user_profile=user_profile_dict,
                        stage_config=next_stage_config,
                        stage_number=next_stage,
                        is_new_stage=True
                    )
                    logger.info(f"User {user_id} progressed from Stage {current_stage} to Stage {next_stage}")
                else:
                    response = self._generate_stage_response(
                        user_input=user_input,
                        user_profile=user_profile_dict,
                        stage_config=stage_config,
                        stage_number=current_stage,
                        is_new_stage=False
                    )
            else:
                response = self._generate_completion_response(user_input, user_profile_dict)
                logger.info(f"User {user_id} completed all lead stages")
        else:
            # Continue with current stage
            response = self._generate_stage_response(
                user_input=user_input,
                user_profile=user_profile_dict,
                stage_config=stage_config,
                stage_number=current_stage,
                is_new_stage=False,
                missing_requirements=stage_completion.get('missing_requirements', [])
            )
        return response
    
    def _generate_stage_response(self, user_input: str, user_profile: dict, 
                               stage_config: Dict, stage_number: int, 
                               is_new_stage: bool, missing_requirements: list = None) -> str:
        """Generate contextual response based on current stage"""
        
        if is_new_stage:
            stage_context = "Great! We're moving forward to the next step."
        else:
            stage_context = "Let's continue with our current focus."
        
        missing_info = ""
        if missing_requirements:
            missing_info = f"To help you better, I'd like to understand: {', '.join(missing_requirements[:2])}"
        
        user_name = user_profile.get("name", "")
        name_part = f"{user_name}, " if user_name else ""
        
        prompt = f"""
You are a helpful sales assistant. Generate a natural, conversational response.

CONTEXT:
- {name_part}you are in Stage {stage_number}: {stage_config['description']}
- {stage_context}
- {missing_info}

USER PROFILE: {json.dumps(user_profile, indent=2)}
USER MESSAGE: {user_input}

Generate a friendly, helpful response that:
1. Acknowledges their message naturally
2. Guides them toward the current stage goal
3. Asks relevant questions to progress the conversation
4. Feels natural and conversational
5. Is helpful and not pushy

Keep response concise (2-3 sentences max).
Be professional but warm and conversational.
"""
        
        try:
            response = call_llm(prompt, temperature=0.7)
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating stage response: {e}")
            # Fallback response
            return f"Thank you for your message! I'm here to help you. {missing_info if missing_info else 'How can I assist you today?'}"
    
    def _generate_completion_response(self, user_input: str, user_profile: dict) -> str:
        """Generate response when all stages are complete"""
        user_name = user_profile.get("name", "")
        name_part = f"{user_name}, " if user_name else ""
        
        prompt = f"""
The user has completed all lead qualification stages. Generate a completion response that:
1. Acknowledges their completion
2. Thanks them for their time and information
3. Mentions next steps (like scheduling a call or connecting with our team)
4. Feels celebratory but professional

USER PROFILE: {json.dumps(user_profile, indent=2)}
USER MESSAGE: {user_input}

Keep it professional, encouraging, and forward-looking.
Address them by name if available: {name_part}
"""
        
        try:
            response = call_llm(prompt, temperature=0.7)
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating completion response: {e}")
            return f"Thank you {name_part}for completing our qualification process! Our team will be in touch with you soon to discuss the next steps."
    
    def _format_conversation(self, conversation_history: list) -> str:
        """Format entire conversation history for LLM context"""
        if not conversation_history:
            return "No previous conversation"

        formatted = []
        for msg in conversation_history:  # Use all messages for context
            if isinstance(msg, dict):
                role = msg.get('role', 'unknown')
                content = msg.get('content', msg.get('message', ''))
                if content:
                    formatted.append(f"{role.upper()}: {content}")

        return "\n".join(formatted) if formatted else "No previous conversation"

# For backward compatibility
def dynamic_lead_conversion_agent(user_input: str, user_profile_dict: dict, profile_key: str) -> str:
    """
    Backward compatible function wrapper
    """
    agent = DynamicLeadConversionAgent()
    return agent.handle(user_input, user_profile_dict, profile_key)
