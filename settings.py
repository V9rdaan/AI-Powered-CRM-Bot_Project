"""
Handles environment variables and API keys.
""" 

import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# ====================
# PostgreSQL Settings
# ====================
POSTGRES_HOST = os.getenv("DB_HOST", "localhost")
POSTGRES_DB = os.getenv("DB_NAME", "CRMChatbot")
POSTGRES_USER = os.getenv("DB_USER", "kartik")
POSTGRES_PASSWORD = os.getenv("DB_PASS", "1234")
POSTGRES_PORT = int(os.getenv("DB_PORT", 5432))

# ====================
# Redis Settings
# ====================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
