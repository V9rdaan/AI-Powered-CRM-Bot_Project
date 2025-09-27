# utils/prompt_generator.py

def get_prompt(user_profile, lead, user_input=None):
    name = user_profile.get("name", "there")
    company = user_profile.get("company")
    email = user_profile.get("email")
    phone = user_profile.get("phone")
    stage = int(lead.get("stage", 0))

    # Build a natural context summary
    context = f"User profile: Name: {name}"
    if company:
        context += f", Company: {company}"
    if email:
        context += f", Email: {email}"
    if phone:
        context += f", Phone: {phone}"
    context += f", Lead stage: {stage}."

    # Add the latest user message
    if user_input:
        context += f" The user just said: '{user_input}'."

    # Give the LLM a general instruction to be helpful and conversational
    prompt = (
        f"{context} "
        "As a helpful CRM assistant, continue the conversation naturally. "
        "You may ask for any missing information if needed, but also feel free to answer questions, offer assistance, or move the conversation forward in a friendly, engaging way."
    )

    return prompt.strip()