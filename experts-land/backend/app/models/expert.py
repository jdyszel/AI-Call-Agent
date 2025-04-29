from sqlalchemy import Column, String, Text, Boolean
from app.db.base import BaseModel

class Expert(BaseModel):
    __tablename__ = "experts"

    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    bio = Column(Text)
    expertise = Column(String(200))
    is_active = Column(Boolean, default=True)
    profile_picture = Column(String(255))
    linkedin_url = Column(String(255))
    github_url = Column(String(255))
    website_url = Column(String(255)) 