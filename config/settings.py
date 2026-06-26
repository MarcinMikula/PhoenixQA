"""
settings.py
Centralized config loader — env vars + .env file.
Single source of truth for all PhoenixQA settings.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    ai_provider: str = os.getenv("AI_PROVIDER", "ollama")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    healing_mode: str = os.getenv("HEALING_MODE", "safe")
    chaos_app_url: str = os.getenv("CHAOS_APP_URL", "http://localhost:5173")
    chaos_level: str = os.getenv("CHAOS_LEVEL", "MEDIUM")  # LOW | MEDIUM | HIGH
    shadow_dom_enabled: bool = os.getenv("SHADOW_DOM_ENABLED", "false").lower() == "true"
    db_path: str = os.getenv("DB_PATH", "phoenix/training/healing_history.db")
    default_timeout: int = int(os.getenv("DEFAULT_TIMEOUT", "10000"))
    healing_timeout: int = int(os.getenv("HEALING_TIMEOUT", "30000"))
