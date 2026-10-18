"""Centralized environment configuration. No secrets or model downloads here."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load .env automatically; real shell variables still take precedence.
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def resolve_path(env_key: str, default: str) -> Path:
    value = Path(os.environ.get(env_key, default)).expanduser()
    return value if value.is_absolute() else ROOT / value


def model_name() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M")


def model_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434")


def backend_name() -> str:
    name = os.getenv("AGENT_BACKEND", "real")
    if name not in {"real", "mock"}:
        raise ValueError("AGENT_BACKEND must be 'real' or 'mock'")
    return name


def attempts_limit() -> int:
    return max(1, min(5, int(os.getenv("MAX_ATTEMPTS", "3"))))


def database_path() -> Path:
    return resolve_path("DATABASE_PATH", "data/shop.duckdb")


def checkpoint_path() -> Path:
    return resolve_path("CHECKPOINT_PATH", "data/checkpoints.sqlite")
