from sqlalchemy import Column, String, Boolean
from app.db.base import BaseModel

class User(BaseModel):
    __tablename__ = "users"

    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String(20), default="user")  # 'admin', 'user', 'manager'

    def __repr__(self):
        return f"<User {self.email}>" 