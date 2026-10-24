from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "Transcribe Hub"
    app_env: str = "development"
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_expire_minutes: int = 60 * 12
    frontend_origin: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:8080"

    database_url: str = "postgresql+psycopg2://hub:hub@localhost:5432/hub"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "transcribe-hub"
    s3_region: str = "us-east-1"

    audiclabs_api_key: str = ""
    audiclabs_base_url: str = "https://api.audiclabs.com/v1"
    audiclabs_demo_fallback: bool = True
    audiclabs_max_file_bytes: int = 100 * 1024 * 1024
    storage_max_file_bytes: int = 10 * 1024 * 1024 * 1024

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Transcribe Hub <noreply@localhost>"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""

    stripe_secret_key: str = ""
    paypal_client_id: str = ""

    google_drive_client_id: str = ""
    google_drive_client_secret: str = ""
    dropbox_app_key: str = ""
    onedrive_client_id: str = ""
    zoom_webhook_secret: str = ""
    teams_webhook_secret: str = ""

    encryption_key: str = "hub-dev-fernet-key-change-me-32bytes!!"


settings = Settings()
