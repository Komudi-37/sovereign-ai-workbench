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

    # CORS — frontend origin allowed to call the API
    frontend_origin: str = "http://localhost:5173"

    class Config:
        # Load from .env file in the backend/ directory
        env_file = ".env"
        env_file_encoding = "utf-8"


# Single shared settings instance used throughout the app
settings = Settings()
