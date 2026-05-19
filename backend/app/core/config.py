from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str

    admin_password: str | None = None
    admin_session_secret: str | None = None
    admin_session_ttl_seconds: int = 43200

    google_drive_oauth_client_id: str | None = None
    google_drive_oauth_client_secret: str | None = None
    google_drive_oauth_refresh_token: str | None = None
    google_drive_folder_id: str | None = None

    face_similarity_threshold: float = 0.50
    yolo_confidence: float = 0.50
    storage_bucket: str = "event-photos"

    class Config:
        env_file = (".env", ".env.local")  # .env.local overrides .env

settings = Settings()
