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

    # Long-Term Memory / Embeddings
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    RETRIEVAL_TAU: float = float(os.getenv("RETRIEVAL_TAU", "0.75"))
    ALLOW_RECENCY_FALLBACK: bool = os.getenv("ALLOW_RECENCY_FALLBACK", "false").lower() in ("true", "1", "yes")
    MEMORY_PER_TURN: bool = os.getenv("MEMORY_PER_TURN", "true").lower() in ("true", "1", "yes")
    PIPELINE_MODE: str = os.getenv("PIPELINE_MODE", "custom").lower()

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context: object) -> None:
        if self.ENVIRONMENT.lower() == "production" and self.ALLOW_DEV_AUTH:
            raise RuntimeError("ALLOW_DEV_AUTH cannot be enabled when ENVIRONMENT=production")


settings = Settings()
