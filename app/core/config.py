import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "VoCall API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Supabase
    NEXT_PUBLIC_SUPABASE_URL: str = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    NEXT_PUBLIC_SUPABASE_ANON_KEY: str = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    ALLOW_DEV_AUTH: bool = os.getenv("ALLOW_DEV_AUTH", "false").lower() in ("true", "1", "yes")

    # LLM Providers
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")

    # Redis
    UPSTASH_REDIS_REST_URL: str = os.getenv("UPSTASH_REDIS_REST_URL", "")
    UPSTASH_REDIS_REST_TOKEN: str = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

    # FalkorDB
    FALKORDB_HOST: str = os.getenv("FALKORDB_HOST", "127.0.0.1")
    FALKORDB_PORT: int = int(os.getenv("FALKORDB_PORT", "6379"))

    # LiveKit
    LIVEKIT_URL: str = os.getenv("LIVEKIT_URL", "")
    LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY", "")
    LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET", "")

    # Public URL
    BACKEND_PUBLIC_URL: str = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")

    # Twilio
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")

    # Voice / STT / TTS
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
    CARTESIA_API_KEY: str = os.getenv("CARTESIA_API_KEY", "")
    HUME_API_KEY: str = os.getenv("HUME_API_KEY", "")

    # Workflows & Messaging
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    TRIGGER_SECRET_KEY: str = os.getenv("TRIGGER_SECRET_KEY", "")

    # LLM Models
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    LLM_FALLBACK_MODEL: str = os.getenv("LLM_FALLBACK_MODEL", "llama3-70b-8192")

    # Long-Term Memory / Embeddings
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    RETRIEVAL_TAU: float = float(os.getenv("RETRIEVAL_TAU", "0.75"))
    EPISODIC_LIMIT: int = int(os.getenv("EPISODIC_LIMIT", "3"))
    ALLOW_RECENCY_FALLBACK: bool = os.getenv("ALLOW_RECENCY_FALLBACK", "false").lower() in ("true", "1", "yes")
    MEMORY_PER_TURN: bool = os.getenv("MEMORY_PER_TURN", "true").lower() in ("true", "1", "yes")
    PIPELINE_MODE: str = os.getenv("PIPELINE_MODE", "custom").lower()

    # Emotion & Intent Parameters
    FUSION_AUDIO_WEIGHT: float = float(os.getenv("FUSION_AUDIO_WEIGHT", "0.6"))
    TONE_THRESHOLD_MILD: float = float(os.getenv("TONE_THRESHOLD_MILD", "0.4"))
    TONE_THRESHOLD_STRONG: float = float(os.getenv("TONE_THRESHOLD_STRONG", "0.6"))
    TONE_THRESHOLD_POSITIVE: float = float(os.getenv("TONE_THRESHOLD_POSITIVE", "0.6"))
    ALERT_THRESHOLD: float = float(os.getenv("ALERT_THRESHOLD", "0.7"))
    INTENT_CONFIDENCE_MIN: float = float(os.getenv("INTENT_CONFIDENCE_MIN", "0.70"))
    SLOT_TTL_SECONDS: int = int(os.getenv("SLOT_TTL_SECONDS", "3600"))

    # Voice Activity Detection (VAD) / Telephone & WebCall Audio Framing
    VAD_ENERGY_THRESHOLD: float = float(os.getenv("VAD_ENERGY_THRESHOLD", "400.0"))
    VAD_FRAME_MS: int = int(os.getenv("VAD_FRAME_MS", "20"))
    VAD_SILENCE_MS: int = int(os.getenv("VAD_SILENCE_MS", "700"))
    VAD_MIN_MS: int = int(os.getenv("VAD_MIN_MS", "120"))
    VAD_MAX_MS: int = int(os.getenv("VAD_MAX_MS", "15000"))

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context: object) -> None:
        if self.ENVIRONMENT.lower() == "production":
            if self.ALLOW_DEV_AUTH:
                raise RuntimeError("ALLOW_DEV_AUTH cannot be enabled when ENVIRONMENT=production")
            if not (self.TWILIO_AUTH_TOKEN and self.TWILIO_AUTH_TOKEN.strip()):
                raise RuntimeError("TWILIO_AUTH_TOKEN must be set when ENVIRONMENT=production")


settings = Settings()


def settings_snapshot() -> dict:
    """Returns a serializable dictionary snapshot of active runtime hyperparameters and settings."""
    return {
        "RETRIEVAL_TOP_K": settings.RETRIEVAL_TOP_K,
        "RETRIEVAL_TAU": settings.RETRIEVAL_TAU,
        "EPISODIC_LIMIT": settings.EPISODIC_LIMIT,
        "FUSION_AUDIO_WEIGHT": settings.FUSION_AUDIO_WEIGHT,
        "TONE_THRESHOLD_MILD": settings.TONE_THRESHOLD_MILD,
        "TONE_THRESHOLD_STRONG": settings.TONE_THRESHOLD_STRONG,
        "TONE_THRESHOLD_POSITIVE": settings.TONE_THRESHOLD_POSITIVE,
        "ALERT_THRESHOLD": settings.ALERT_THRESHOLD,
        "LLM_MODEL": settings.LLM_MODEL,
        "LLM_FALLBACK_MODEL": settings.LLM_FALLBACK_MODEL,
        "EMBEDDING_PROVIDER": settings.EMBEDDING_PROVIDER,
        "EMBEDDING_MODEL": settings.EMBEDDING_MODEL,
        "EMBEDDING_DIM": settings.EMBEDDING_DIM,
        "INTENT_CONFIDENCE_MIN": settings.INTENT_CONFIDENCE_MIN,
        "SLOT_TTL_SECONDS": settings.SLOT_TTL_SECONDS,
        "ALLOW_RECENCY_FALLBACK": settings.ALLOW_RECENCY_FALLBACK,
        "MEMORY_PER_TURN": settings.MEMORY_PER_TURN,
        "PIPELINE_MODE": settings.PIPELINE_MODE,
        "ENVIRONMENT": settings.ENVIRONMENT,
        "VAD_ENERGY_THRESHOLD": settings.VAD_ENERGY_THRESHOLD,
        "VAD_FRAME_MS": settings.VAD_FRAME_MS,
        "VAD_SILENCE_MS": settings.VAD_SILENCE_MS,
        "VAD_MIN_MS": settings.VAD_MIN_MS,
        "VAD_MAX_MS": settings.VAD_MAX_MS,
    }
