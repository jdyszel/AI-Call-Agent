from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import relationship
from app.db.base import BaseModel

class Role(BaseModel):
    __tablename__ = "roles"

    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    
    # Permission flags
    can_manage_users = Column(Boolean, default=False)
    can_manage_experts = Column(Boolean, default=False)
    can_view_experts = Column(Boolean, default=True)
    can_edit_experts = Column(Boolean, default=False)
    can_delete_experts = Column(Boolean, default=False)
    
    # Relationships
    users = relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>" 