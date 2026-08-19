from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.evaluations import router as evaluations_router
from app.api.jobs import router as jobs_router
from app.api.materials import router as materials_router
from app.api.recordings import router as recordings_router
from app.api.sentences import router as sentences_router
from app.api.system import router as system_router
from app.api.words import router as words_router
from app.api.providers import router as providers_router
from app.api.text_practices import router as text_practices_router
from app.api.language_preferences import router as language_preferences_router
from app.core.config import settings
from app.core.migrations import run_migrations
from app.services.job_service import start_job_worker, stop_job_worker
from app.services.media_service import ensure_directories
from app.services.ai.http_transport import close_provider_http_client
import app.models  # noqa: F401

app = FastAPI(title=settings.app_name, version=settings.app_version, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    ensure_directories()
    run_migrations()
    start_job_worker()


@app.on_event("shutdown")
async def on_shutdown():
    await stop_job_worker()
    close_provider_http_client()


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version}


app.include_router(materials_router)
app.include_router(sentences_router)
app.include_router(recordings_router)
app.include_router(evaluations_router)
app.include_router(jobs_router)
app.include_router(system_router)
app.include_router(words_router)
app.include_router(providers_router)
app.include_router(text_practices_router)
app.include_router(language_preferences_router)
