"""
Interest Agent: Analyzes conversation history to determine user interest level
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any
from utils.call_llm import call_llm
from database.redis_client import get_conversation_history
from database.postgres_client import fetch_crm_data, upsert_crm_data

logger = logging.getLogger(__name__)

class InterestAgent:
    def __init__(self):
        self.interest_prompt = """
Analyze this conversation between a sales chatbot and a potential customer to determine their genuine interest level.

CONVERSATION:
{conversation}

USER PROFILE:
{profile}

Determine the user's interest level based on:
- Engagement quality and depth
- Information sharing willingness  
- Questions about products/services
- Buying signals or objections
- Overall conversation tone

Respond with only this JSON format:
{{
    "interest_level": "HIGH|MEDIUM|LOW|NONE", 
    "confidence": 0.85,
    "reasoning": "Brief explanation of the assessment"
}}
"""

    def analyze_user_interest(self, user_id: str) -> Dict[str, Any]:
        """Analyze conversation and determine user interest level"""
        try:
            logger.info(f"[InterestAgent] Analyzing interest for user: {user_id}")
            
            # Get conversation from Redis
            conversation = get_conversation_history(user_id)
            if not conversation:
                return {"interest_level": "NONE", "confidence": 0.0, "reasoning": "No conversation found"}
            
            # Get user profile
            crm_data = fetch_crm_data(user_id)
            profile = crm_data.get("profile_data", {}) if crm_data else {}
            
            # Format conversation for analysis
            formatted_conversation = self._format_conversation(conversation)
            
            # Get LLM analysis
            prompt = self.interest_prompt.format(
                conversation=formatted_conversation,
                profile=profile
            )
            
            response = call_llm(prompt)
            
            # Parse JSON response
            try:
                result = json.loads(response)
                logger.info(f"[InterestAgent] Interest analysis: {result.get('interest_level')} ({result.get('confidence', 0):.2f})")
                return result
            except json.JSONDecodeError:
                logger.error(f"[InterestAgent] Failed to parse LLM response: {response}")
                return {"interest_level": "UNKNOWN", "confidence": 0.0, "reasoning": "Analysis error"}
                
        except Exception as e:
            logger.error(f"[InterestAgent] Error analyzing interest: {e}")
            return {"interest_level": "ERROR", "confidence": 0.0, "reasoning": str(e)}
    
    def _format_conversation(self, conversation) -> str:
        """Format conversation for LLM analysis"""
        formatted = []
        for i, msg in enumerate(conversation, 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            formatted.append(f"[{i}] {role.upper()}: {content}")
        return "\n".join(formatted)
    
    def save_interest_to_crm(self, user_id: str, interest_data: Dict[str, Any]) -> bool:
        """Save interest analysis to CRM database as JSON in user_interest column"""
        try:
            # Get existing CRM data
            existing = fetch_crm_data(user_id)
            if not existing:
                logger.warning(f"[InterestAgent] No CRM data found for user: {user_id}")
                return False

            # Update lead_data with interest information (for backward compatibility)
            profile_data = existing.get("profile_data", {})
            lead_data = existing.get("lead_data", {})

            # Add interest field to lead_data
            lead_data["interest"] = interest_data.get("interest_level", "UNKNOWN")
            lead_data["interest_confidence"] = interest_data.get("confidence", 0.0)
            lead_data["interest_reasoning"] = interest_data.get("reasoning", "")

            # Create JSON object for user_interest column
            user_interest_json = {
                "user_interest": interest_data.get("interest_level", "UNKNOWN"),
                "interest_reasoning": interest_data.get("reasoning", ""),
                "confidence": interest_data.get("confidence", 0.0),
                "analyzed_at": str(datetime.now())
            }

            # Save to CRM with JSON in user_interest column
            success = upsert_crm_data(
                user_id,
                profile_data,
                lead_data,
                json.dumps(user_interest_json)  # Store as JSON string
            )

            if success:
                logger.info(f"[InterestAgent] ✅ Interest JSON saved to CRM: {user_id} - {interest_data.get('interest_level')}")
            else:
                logger.error(f"[InterestAgent] ❌ Failed to save interest to CRM: {user_id}")

            return success

        except Exception as e:
            logger.error(f"[InterestAgent] Error saving interest to CRM: {e}")
            return False
    
    def process_interest_analysis(self, user_id: str) -> Dict[str, Any]:
        """Main method to analyze and save interest"""
        logger.info(f"[InterestAgent] 🔍 Processing interest analysis for: {user_id}")
        
        # Analyze interest
        interest_result = self.analyze_user_interest(user_id)
        
        # Save to CRM
        saved = self.save_interest_to_crm(user_id, interest_result)
        
        return {
            "user_id": user_id,
            "interest_analysis": interest_result,
            "saved_to_crm": saved
        }
