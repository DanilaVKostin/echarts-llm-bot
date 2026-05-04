from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_ENV_FILE_PATHS = tuple(
    str(p)
    for p in (_BACKEND_DIR / ".env", _REPO_ROOT / ".env")
    if p.is_file()
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATHS if _ENV_FILE_PATHS else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LLM_LOCAL_BASE_URL: str = "http://localhost:11434/v1"
    LLM_LOCAL_API_KEY: str = "ollama"
    LLM_LOCAL_MODEL: str = "qwen2.5:7b"
    LLM_LOCAL_MODEL_QWEN35_9B: str = "qwen3.5:9b"
    LLM_LOCAL_MODEL_QWEN3_CODER_30B: str = "qwen3-coder:30b"

    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL_QWEN35_27B: str = "qwen/qwen3.6-27b"
    OPENROUTER_MODEL_GPT4O: str = "openai/gpt-4o"

    LLM_MAX_RETRIES: int = 2
    LLM_HTTP_TIMEOUT: float = 120.0
    LLM_TEMPERATURE: float = 0.1

    RAG_ENABLED: bool = True
    RAG_CHROMA_PATH: str = "./data/chroma_db"
    RAG_CHROMA_COLLECTION: str = "echarts"
    INDICATOR_CHROMA_COLLECTION: str = "indicators"
    INDICATOR_EMBEDDING_PROVIDER: str = "sentence_transformers"
    INDICATOR_EMBEDDING_MODEL: str = "ai-forever/FRIDA"
    RAG_EMBEDDING_URL: str = "http://localhost:11434/api/embed"
    RAG_EMBEDDING_MODEL: str = "nomic-embed-text"
    RAG_TOP_K: int = 5

    DATABASE_URL: str = ""


settings = Settings()
