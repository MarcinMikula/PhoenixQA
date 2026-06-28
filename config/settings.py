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
    healing_mode: str = os.getenv("HEALING_MODE", "safe")  # safe | autonomous

    # Autonomous Mode policy (Sprint 5) — only consulted when
    # healing_mode == "autonomous". See AutonomousPolicy for defaults if
    # any of these are left unset.
    autonomous_min_confidence: float = float(os.getenv("AUTONOMOUS_MIN_CONFIDENCE", "0.75"))
    autonomous_max_attempts_total: int = int(os.getenv("AUTONOMOUS_MAX_ATTEMPTS_TOTAL", "5"))
    autonomous_max_input_tokens: int = int(os.getenv("AUTONOMOUS_MAX_INPUT_TOKENS", "50000"))
    autonomous_max_output_tokens: int = int(os.getenv("AUTONOMOUS_MAX_OUTPUT_TOKENS", "10000"))
    autonomous_max_time_per_heal_ms: int = int(os.getenv("AUTONOMOUS_MAX_TIME_PER_HEAL_MS", "60000"))
    chaos_app_url: str = os.getenv("CHAOS_APP_URL", "http://localhost:5173")
    chaos_level: str = os.getenv("CHAOS_LEVEL", "MEDIUM")  # LOW | MEDIUM | HIGH
    shadow_dom_enabled: bool = os.getenv("SHADOW_DOM_ENABLED", "false").lower() == "true"
    db_path: str = os.getenv("DB_PATH", "phoenix/training/healing_history.db")
    default_timeout: int = int(os.getenv("DEFAULT_TIMEOUT", "10000"))
    healing_timeout: int = int(os.getenv("HEALING_TIMEOUT", "30000"))
