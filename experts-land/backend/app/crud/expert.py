from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.expert import Expert
from app.schemas.expert import ExpertCreate, ExpertUpdate

def get_expert(db: Session, expert_id: int) -> Optional[Expert]:
    return db.query(Expert).filter(Expert.id == expert_id).first()

def get_expert_by_email(db: Session, email: str) -> Optional[Expert]:
    return db.query(Expert).filter(Expert.email == email).first()

def get_experts(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    is_active: Optional[bool] = None
) -> List[Expert]:
    query = db.query(Expert)
    if is_active is not None:
        query = query.filter(Expert.is_active == is_active)
    return query.offset(skip).limit(limit).all()

def create_expert(db: Session, expert: ExpertCreate) -> Expert:
    db_expert = Expert(**expert.model_dump())
    db.add(db_expert)
    db.commit()
    db.refresh(db_expert)
    return db_expert

def update_expert(
    db: Session, 
    expert_id: int, 
    expert: ExpertUpdate
) -> Optional[Expert]:
    db_expert = get_expert(db, expert_id)
    if db_expert:
        update_data = expert.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_expert, key, value)
        db.commit()
        db.refresh(db_expert)
    return db_expert

def delete_expert(db: Session, expert_id: int) -> Optional[Expert]:
    db_expert = get_expert(db, expert_id)
    if db_expert:
        db.delete(db_expert)
        db.commit()
    return db_expert 