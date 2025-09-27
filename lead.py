"""
Data models for leads.
""" 

# models/lead.py
from typing import Optional
from pydantic import BaseModel

class Lead(BaseModel):
    stage: int
    source: Optional[str] = None
    interested_in: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
