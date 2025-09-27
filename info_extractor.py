import os
import openai
import json
import re
from dotenv import load_dotenv
from config.prompts import INFO_EXTRACTION_PROMPT

load_dotenv()

# Get the OpenAI API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables. Please set it in your .env file.")

# Initialize OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

def extract_info(current_profile: dict, new_message: str) -> dict:
    """
    Update the user's profile by extracting new information from the latest message.
    Returns the updated profile as a flat JSON object.
    """
    # Fill in the profiling prompt
    formatted_prompt = INFO_EXTRACTION_PROMPT[0]\
        .replace("[current_profile]", json.dumps(current_profile))\
        .replace("[new_message]", new_message.strip())

    try:
        
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a profiling assistant. Your job is to extract structured user profile data from each "
                        "message and return an updated flat JSON object. IMPORTANT: Return ONLY valid JSON - no explanations, "
                        "no markdown code blocks, no extra text. Use double quotes for all strings. Example format: "
                        
                    )
                },
                {
                    "role": "user",
                    "content": formatted_prompt
                }
            ]
        )

        content = response.choices[0].message.content.strip()
        
        # Debug: Print the raw content to see what we're getting
        print(f"[DEBUG] Raw LLM response: {repr(content)}")

        # Clean the content - remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]  # Remove ```json
        if content.startswith("```"):
            content = content[3:]   # Remove ```
        if content.endswith("```"):
            content = content[:-3]  # Remove trailing ```
        
        content = content.strip()
        
        # If content doesn't start with {, try to find JSON
        if not content.startswith('{'):
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                content = match.group(0)
            else:
                print(f"[Warning] No JSON found in response: {content}")
                return current_profile

        # Try to parse response directly
        try:
            parsed_json = json.loads(content)
            return parsed_json

        # Fallback: try to fix common JSON issues
        except json.JSONDecodeError as e:
            print(f"[Warning] JSON decode error: {e}")
            print(f"[Warning] Problematic content: {repr(content)}")
            
            # Try to fix common issues
            try:
                # Fix single quotes to double quotes
                fixed_content = content.replace("'", '"')
                # Fix trailing commas
                fixed_content = re.sub(r',(\s*[}\]])', r'\1', fixed_content)
                return json.loads(fixed_content)
            except json.JSONDecodeError:
                print("[Warning] Failed to parse JSON after fixes. Returning current profile.")
                return current_profile

    except Exception as exc:
        print("[Error in extract_info]:", exc)
        return current_profile