"""
PhoenixQA entry point.
Usage: python -m phoenix
"""
import sys
from config.settings import Settings


def main():
    settings = Settings()
    print(f"🔥 PhoenixQA starting...")
    print(f"   AI Provider : {settings.ai_provider}")
    print(f"   Healing Mode: {settings.healing_mode}")
    print(f"   Chaos Level : {settings.chaos_level}")
    print(f"   Chaos App   : {settings.chaos_app_url}")
    print()
    print("Run pytest to execute tests:")
    print("  pytest tests/chaos/ -m chaos")


if __name__ == "__main__":
    main()
