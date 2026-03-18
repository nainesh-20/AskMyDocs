from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_storage_bucket: str = "private_rag"

    # PostgreSQL
    database_url: str

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection_name: str = "rag_documents"

    # LLM
    groq_api_key: str
    groq_model: str = "llama-3.1-8b-instant"

    # RAG thresholds
    confidence_threshold: float = 0.75
    no_match_threshold: float = 0.45

    # Limits
    max_documents_per_user: int = 3

    # App
    environment: str = "development"
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()  # type: ignore[call-arg]
