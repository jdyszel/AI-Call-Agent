from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import expert as crud
from app.schemas.expert import Expert, ExpertCreate, ExpertUpdate

router = APIRouter()

@router.get("/", response_model=List[Expert])
def read_experts(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    is_active: bool = Query(None, description="Filter by active status")
):
    """
    Retrieve experts.
    """
    experts = crud.get_experts(db, skip=skip, limit=limit, is_active=is_active)
    return experts

@router.post("/", response_model=Expert)
def create_expert(
    *,
    db: Session = Depends(deps.get_db),
    expert_in: ExpertCreate
):
    """
    Create new expert.
    """
    expert = crud.get_expert_by_email(db, email=expert_in.email)
    if expert:
        raise HTTPException(
            status_code=400,
            detail="The expert with this email already exists in the system.",
        )
    expert = crud.create_expert(db=db, expert=expert_in)
    return expert

@router.get("/{expert_id}", response_model=Expert)
def read_expert(
    expert_id: int,
    db: Session = Depends(deps.get_db),
):
    """
    Get expert by ID.
    """
    expert = crud.get_expert(db, expert_id=expert_id)
    if expert is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    return expert

@router.put("/{expert_id}", response_model=Expert)
def update_expert(
    *,
    db: Session = Depends(deps.get_db),
    expert_id: int,
    expert_in: ExpertUpdate
):
    """
    Update an expert.
    """
    expert = crud.get_expert(db, expert_id=expert_id)
    if expert is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    expert = crud.update_expert(db=db, expert_id=expert_id, expert=expert_in)
    return expert

@router.delete("/{expert_id}", response_model=Expert)
def delete_expert(
    *,
    db: Session = Depends(deps.get_db),
    expert_id: int,
):
    """
    Delete an expert.
    """
    expert = crud.get_expert(db, expert_id=expert_id)
    if expert is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    expert = crud.delete_expert(db=db, expert_id=expert_id)
    return expert 