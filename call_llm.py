# utils/call_llm.py (compatible with openai>=1.0.0)
import os
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def call_llm(prompt: str, model: str = "gpt-4.1-mini", temperature: float = 0.5) -> str:
    try:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[LLM Error] {str(e)}"
