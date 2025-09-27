from config.prompts import PROMPT_AGENT_TEMPLATE, PROMPT_AGENT_REFINE_TEMPLATE
from utils.prompt_generator import get_prompt
from utils.call_llm import call_llm  # ✅ import
import logging
logger = logging.getLogger(__name__)

class PromptAgent:
    def handle(self, user_profile, lead, user_input, previous_response=None, user_id=None, original_stage_response=None):
        lead_stage = lead.get("stage")
        if not lead_stage:
            raise ValueError("[PromptAgent] Missing 'stage' in lead")

        # Generate dynamic context (no conversation history)
        dynamic_prompt = get_prompt(user_profile, lead, user_input)

        if previous_response:
            # Refine the previous response using only current context, now centralized
            final_prompt = PROMPT_AGENT_REFINE_TEMPLATE.format(
                user_input=user_input,
                user_profile=user_profile,
                lead_stage=lead_stage,
                previous_response=previous_response,
                original_stage_response=original_stage_response or ""
            )
            response = call_llm(final_prompt, model="gpt-4.1-mini", temperature=0.3)
            logger.info(f"[PromptAgent] Refined response: {response}")
            return response
        else:
            # Generate new response using only current context and template
            final_prompt = PROMPT_AGENT_TEMPLATE.format(
                previous_response=previous_response or "",
                user_profile=user_profile,
                conversation_history="",  # No history
                user_message=user_input,
                dynamic_prompt=dynamic_prompt,
                original_stage_response=original_stage_response or ""
            )
            response = call_llm(final_prompt, model="gpt-4.1-mini", temperature=0.3)
            logger.info(f"[PromptAgent] Generated new response: {response}")
            return response
