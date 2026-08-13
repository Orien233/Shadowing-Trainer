from fastapi import APIRouter, status

from app.schemas.system import ShutdownResponse
from app.services.system_service import schedule_backend_shutdown

router = APIRouter(prefix="/api/system", tags=["system"])


@router.post("/shutdown", response_model=ShutdownResponse, status_code=status.HTTP_202_ACCEPTED)
def shutdown_backend():
    schedule_backend_shutdown()
    return ShutdownResponse(detail="Backend shutdown scheduled.")
