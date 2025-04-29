from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional
from datetime import datetime

class ExpertBase(BaseModel):
    name: str
    email: EmailStr
    bio: Optional[str] = None
    expertise: Optional[str] = None
    profile_picture: Optional[str] = None
    linkedin_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    website_url: Optional[HttpUrl] = None

class ExpertCreate(ExpertBase):
    pass

class ExpertUpdate(ExpertBase):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

class ExpertInDB(ExpertBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Expert(ExpertInDB):
    pass 