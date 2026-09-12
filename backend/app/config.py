"""
Configuration module for Sovereign AI Workbench backend.

Loads settings from environment variables (with .env file support).
All configuration is centralized here — no hardcoded values in routes or services.
"""

from pathlib import Path
from pydantic_settings import BaseSettings

_app_dir = Path(__file__).resolve().parent
_backend_dir = _app_dir.parent
_repo_root = _backend_dir.parent if _backend_dir.name == "backend" else _backend_dir

_default_data_dir = str(_repo_root / "data")
_default_output_dir = str(_repo_root / "outputs")
_default_vector_path = str(_repo_root / "data" / "vector")
_default_db_url = f"sqlite:///{(_repo_root / 'data' / 'sovereign.db').as_posix()}"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Ollama configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout: int = 180  # seconds — CPU inference can be slow

    # Model routing
    fast_model: str = "qwen3:4b"
    reasoning_model: str = "qwen3:4b"
    vision_model: str = "llava:7b"
    embedding_model: str = "nomic-embed-text"

    # Database
    database_url: str = _default_db_url

    # Storage paths
    data_dir: str = _default_data_dir
    output_dir: str = _default_output_dir
    vector_store_path: str = _default_vector_path

    # CORS — frontend origin allowed to call the API
    frontend_origin: str = "http://localhost:5173"

    # File upload
    max_upload_size_mb: int = 50

    # Report
    report_formats: str = "docx,pdf,pptx,xlsx"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Single shared settings instance used throughout the app
settings = Settings()
