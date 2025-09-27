"""
Data models for user profiles.
""" 

# models/userprofile.py
from typing import Optional
from pydantic import BaseModel

class UserProfile(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    interest: Optional[str] = None

    model_config = {"extra": "allow"}  # Pydantic v2 way to allow extra fields
