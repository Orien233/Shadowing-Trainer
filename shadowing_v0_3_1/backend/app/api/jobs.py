from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.database import get_session
from app.models.job import Job
from app.schemas.job import JobRead
from app.services.job_service import retry_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("/{job_id}/retry", response_model=JobRead)
def retry_failed_job(job_id: str, session: Session = Depends(get_session)):
    try:
        return retry_job(session, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
