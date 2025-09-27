"""
Redis connection and memory management.
"""

import os
import redis
from dotenv import load_dotenv
import json
import logging

# Initialize logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Redis client
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def set_user_profile(user_id, profile_dict):
    """
    Stores user profile data in Redis hash.
    Converts all values to strings or JSON-encoded strings.
    Filters out None values.
    """
    key = f"user_profile:{user_id}"
    
    to_store = {
        k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        for k, v in profile_dict.items()
        if v is not None
    }

    logger.info(f"Saving to Redis for {user_id}: {to_store}")
    redis_client.hset(key, mapping=to_store)

def get_user_profile(user_id):
    """
    Retrieves the user profile from Redis and attempts to parse JSON values.
    """
    key = f"user_profile:{user_id}"
    result = redis_client.hgetall(key)

    parsed_result = {}
    for k, v in result.items():
        try:
            parsed_result[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            parsed_result[k] = v

    return parsed_result


def append_conversation_message(user_id, role, content):
    """
    Appends a message (user or bot) to the user's conversation history in Redis as JSON.
    Each message is a dict: {"role": "user"|"bot", "content": ...}
    """
    key = f"chat:{user_id}"
    message = {"role": role, "content": content}
    redis_client.rpush(key, json.dumps(message))
    logger.info(f"Appended message to {key}: {message}")


def get_conversation_history(user_id, limit=None):
    """
    Retrieves conversation messages for a user from Redis.
    Returns a list of dicts (JSON objects).

    Args:
        user_id: The user identifier
        limit: Maximum number of messages to retrieve. If None, retrieves all messages.
    """
    key = f"chat:{user_id}"

    if limit is None:
        # Get all messages
        messages = redis_client.lrange(key, 0, -1)
    else:
        # Get the most recent 'limit' messages
        messages = redis_client.lrange(key, -limit, -1)

    history = []
    for msg in messages:
        try:
            history.append(json.loads(msg))
        except Exception:
            continue
    return history