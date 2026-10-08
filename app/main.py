import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.services.voice_pipeline import get_active_pipeline_path

# Import API Routers
from app.routers import (
    auth,
    agents,
    calls,
    contacts,
    connectors,
    phone_numbers,
    api_keys,
    webhooks,
    memory,
    emotion,
    intent,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)


@app.on_event("startup")
async def startup_event():
    if settings.ENVIRONMENT.lower() == "production":
        if settings.ALLOW_DEV_AUTH:
            raise RuntimeError("ALLOW_DEV_AUTH cannot be enabled when ENVIRONMENT=production")
        if not (settings.TWILIO_AUTH_TOKEN and settings.TWILIO_AUTH_TOKEN.strip()):
            raise RuntimeError("TWILIO_AUTH_TOKEN must be set when ENVIRONMENT=production")
    active_path = get_active_pipeline_path()
    logger.info("VoCall Voice Pipeline Startup: Active pipeline path is [%s]", active_path)


# CORS middleware for Next.js & Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API V1 Routers
api_v1_prefix = settings.API_V1_STR

app.include_router(auth.router, prefix=api_v1_prefix)
app.include_router(agents.router, prefix=api_v1_prefix)
app.include_router(calls.router, prefix=api_v1_prefix)
app.include_router(contacts.router, prefix=api_v1_prefix)
app.include_router(connectors.router)  # Handles /api/connectors
app.include_router(phone_numbers.router, prefix=api_v1_prefix)
app.include_router(api_keys.router, prefix=api_v1_prefix)
app.include_router(webhooks.router, prefix=api_v1_prefix)
app.include_router(memory.router, prefix=api_v1_prefix)
app.include_router(emotion.router, prefix=api_v1_prefix)
app.include_router(intent.router, prefix=api_v1_prefix)



@app.get("/")
def root():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.VERSION}
