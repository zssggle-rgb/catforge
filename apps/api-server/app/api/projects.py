from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CategoryProject
from app.schemas.api import ProjectCreate, ProjectOut

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> CategoryProject:
    project = CategoryProject(
        name=payload.name,
        category_code=payload.category_code,
        description=payload.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[CategoryProject]:
    return list(db.execute(select(CategoryProject).order_by(CategoryProject.created_at.desc())).scalars())


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)) -> CategoryProject:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project

