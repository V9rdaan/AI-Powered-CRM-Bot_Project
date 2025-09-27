
import logging
from utils.call_llm import call_llm
from config.prompts import REFLECTION_AGENT_VALIDATION_PROMPT
import json
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime

logger = logging.getLogger("ReflectionAgent")

class ReflectionAgent:
    def __init__(self):
        self.conversation_profiles = {}
        self.validation_history = []
        
    def profile_conversation_context(
        self, user_id: str, user_message: str, 
        profile_data: Dict, response_history: Optional[List] = None
    ) -> Dict[str, Any]:
        """
        Create simple conversation profile for additional context (optional).
        """
        try:
            conversation_context = self._get_conversation_context(
                user_id, user_message, profile_data, response_history
            )
            return {
                "user_id": user_id,
                "current_message": user_message,
                "profile_data": profile_data,
                "conversation_history": conversation_context.get("conversation_history", []),
                "response_history": response_history or []
            }
        except Exception as e:
            logger.error(f"Error gathering conversation context: {e}")
            return {"user_id": user_id, "current_message": user_message}
    
    def validate_with_profiling(
        self, response: str, lead_goal: str, user_input: str,
        user_id: Optional[str] = None, profile_data: Optional[Dict] = None, 
        response_history: Optional[List] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Enhanced validation using the configured prompt with profiling context.
        """
        if "LLM Error" in response:
            logger.warning("Skipping validation due to LLM error.")
            return True, {"skip_reason": "llm_error"}
        conversation_profile = {}
        if user_id and profile_data:
            try:
                conversation_profile = self.profile_conversation_context(
                    user_id, user_input, profile_data, response_history
                )
            except Exception as e:
                logger.warning(f"Error creating profile, continuing without: {e}")
        validation_prompt = REFLECTION_AGENT_VALIDATION_PROMPT.format(
            user_message=user_input,
            lead_goal=lead_goal,
            assistant_response=response
        )
        try:
            validation_result = call_llm(validation_prompt, model="gpt-4.1-mini", temperature=0.1)
            result_text = validation_result.strip().lower()
            overall_pass = "no" not in result_text
            validation_data = {
                "overall_validation": "pass" if overall_pass else "fail",
                "confidence_score": 0.8 if overall_pass else 0.2,
                "method": "enhanced_with_config_prompt",
                "raw_result": validation_result,
                "reasoning": validation_result
            }
            self._store_validation_history(user_input, response, validation_data, conversation_profile)
            logger.info(f"Enhanced validation (config prompt): {overall_pass} | Reasoning: {validation_result}")
            return overall_pass, validation_data
        except Exception as e:
            logger.error(f"Error in enhanced validation: {e}")
            is_valid = self.validate(response, lead_goal, user_input)
            return is_valid, {"error": str(e), "fallback": True}
    
    def validate_simple(
        self, response: str, lead_goal: str, user_input: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Simple validation method using the configured prompt from config.
        """
        if "LLM Error" in response:
            logger.warning("Skipping validation due to LLM error.")
            return True, {"skip_reason": "llm_error"}
        validation_prompt = REFLECTION_AGENT_VALIDATION_PROMPT.format(
            user_message=user_input,
            lead_goal=lead_goal,
            assistant_response=response
        )
        try:
            result = call_llm(validation_prompt, model="gpt-4.1-mini", temperature=0.1).strip().lower()
            logger.info(f"Simple validation result: {result}")
            is_valid = "no" not in result
            validation_data = {
                "overall_validation": "pass" if is_valid else "fail",
                "confidence_score": 0.8 if is_valid else 0.2,
                "method": "simple_with_config_prompt",
                "raw_result": result
            }
            self._store_validation_history(user_input, response, validation_data, {})
            return is_valid, validation_data
        except Exception as e:
            logger.error(f"Error in simple validation: {e}")
            return True, {"error": str(e), "method": "error_fallback"}
    
    def get_improvement_suggestions(self, validation_data: Dict[str, Any]) -> List[str]:
        """
        Extract actionable improvement suggestions from validation results
        """
        suggestions = validation_data.get("improvement_suggestions", [])
        
        # Add specific suggestions based on low scores
        scores = {
            "alignment_with_goal": "Better align response with the specific lead conversion goal",
            "conversion_effectiveness": "Include stronger conversion elements (CTA, value proposition, urgency)",
            "user_message_relevance": "More directly address the user's specific question or concern",
            "trust_building": "Add credibility indicators (expertise, testimonials, guarantees)",
            "clarity_and_next_steps": "Provide clearer next steps or call-to-action"
        }
        
        for metric, suggestion in scores.items():
            if validation_data.get(metric, 1.0) < 0.7:
                suggestions.append(suggestion)
        
        return list(set(suggestions))  # Remove duplicates
    
    def _get_conversation_context(self, user_id: str, user_message: str, 
                                 profile_data: Dict, response_history: List) -> Dict:
        """
        Gather conversation context from various sources
        """
        context = {
            "user_id": user_id,
            "current_message": user_message,
            "profile_data": profile_data,
            "response_history": response_history or []
        }
        
        # Try to get additional context from database if available
        try:
            from database.redis_client import get_conversation_history
            db_history = get_conversation_history(user_id, limit=10)
            context["conversation_history"] = db_history
        except Exception as e:
            logger.warning(f"Could not fetch conversation history: {e}")
            context["conversation_history"] = []
        return context
    
    def _store_validation_history(self, user_input: str, response: str, 
                                 validation_data: Dict, conversation_profile: Dict):
        """
        Store validation history for analysis and improvement
        """
        self.validation_history.append({
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "response": response,
            "validation_result": validation_data,
            "conversation_profile": conversation_profile
        })
        
        # Keep only last 100 validations to prevent memory issues
        if len(self.validation_history) > 100:
            self.validation_history = self.validation_history[-100:]
    
    def get_validation_analytics(self) -> Dict[str, Any]:
        """
        Get analytics from validation history
        """
        if not self.validation_history:
            return {"message": "No validation history available"}
        
        recent = self.validation_history[-20:]  # Last 20 validations
        
        # Calculate metrics
        total_validations = len(recent)
        passed_validations = sum(1 for v in recent 
                               if v.get("validation_result", {}).get("overall_validation") == "pass")
        
        avg_confidence = sum(v.get("validation_result", {}).get("confidence_score", 0) 
                           for v in recent) / total_validations if total_validations > 0 else 0
        
        # Common improvement areas
        all_weaknesses = []
        for v in recent:
            weaknesses = v.get("validation_result", {}).get("weaknesses", [])
            all_weaknesses.extend(weaknesses)
        
        weakness_counts = {}
        for weakness in all_weaknesses:
            weakness_counts[weakness] = weakness_counts.get(weakness, 0) + 1
        
        return {
            "total_recent_validations": total_validations,
            "pass_rate": round(passed_validations / total_validations, 2) if total_validations > 0 else 0,
            "average_confidence": round(avg_confidence, 2),
            "common_weaknesses": dict(sorted(weakness_counts.items(), 
                                           key=lambda x: x[1], reverse=True)[:5]),
            "total_history_length": len(self.validation_history)
        }
    
    # Legacy method for backward compatibility with your existing graph
    def validate(self, response: str, lead_goal: str, user_input: str) -> bool:
        """
        Legacy validation method - maintains compatibility with existing graph
        """
        if "LLM Error" in response:
            logger.warning("Skipping validation due to LLM error.")
            return True
        validation_prompt = REFLECTION_AGENT_VALIDATION_PROMPT.format(
            user_message=user_input,
            lead_goal=lead_goal,
            assistant_response=response
        )
        try:
            result = call_llm(validation_prompt, model="gpt-4.1-mini", temperature=0.1).strip().lower()
            logger.info(f"LLM validation result: {result}")
            is_valid = "no" not in result
            self._store_validation_history(user_input, response, 
                                         {"overall_validation": "pass" if is_valid else "fail",
                                          "method": "legacy"}, {})
            return is_valid
        except Exception as e:
            logger.error(f"Error in legacy validation: {e}")
            return False