from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    can_manage_users: bool = False
    can_manage_experts: bool = False
    can_view_experts: bool = True
    can_edit_experts: bool = False
    can_delete_experts: bool = False

class RoleCreate(RoleBase):
    pass

class RoleUpdate(RoleBase):
    name: Optional[str] = None

class RoleInDBBase(RoleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Role(RoleInDBBase):
    pass 