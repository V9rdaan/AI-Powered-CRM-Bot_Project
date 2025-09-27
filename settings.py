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
POSTGRES_HOST = os.getenv("DB_HOST", "")
POSTGRES_DB = os.getenv("DB_NAME", "")
POSTGRES_USER = os.getenv("DB_USER", "")
POSTGRES_PASSWORD = os.getenv("DB_PASS", "")
POSTGRES_PORT = int(os.getenv("DB_PORT", ))

# ====================
# Redis Settings
# ====================
REDIS_URL = os.getenv("REDIS_URL", "")


