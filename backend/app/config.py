"""
Configuration module for Sovereign AI Workbench backend.

Loads settings from environment variables (with .env file support).
All configuration is centralized here — no hardcoded values in routes or services.
"""

from pydantic_settings import BaseSettings


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
    database_url: str = "sqlite:///./data/sovereign.db"

    # Storage paths
    data_dir: str = "./data"
    output_dir: str = "./outputs"
    vector_store_path: str = "./data/vector"

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
