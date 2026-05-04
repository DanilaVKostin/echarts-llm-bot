"""
Централизованная конфигурация логирования.

Все записи логов пишутся в формате JSON-lines в:
  logs/app.log      – общий лог (все события)
  logs/llm.log      – только трафик LLM (запросы и ответы)
  logs/requests.log – одна запись на запрос пользователя с полной трассировкой пайплайна

Папка `logs/` определяется относительно рабочей директории
(т.е. папки `backend/` при запуске uvicorn из неё).
"""

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

# ── Убедиться, что директория logs/ существует ───────────────────────────────

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)


# ── JSON-форматтер ───────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Записывает каждую запись лога как одну строку JSON."""

    # Все встроенные атрибуты LogRecord — не передавать их как дополнительные поля
    _RESERVED: frozenset[str] = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Прикрепить все дополнительные поля, переданные через `extra=`
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def _make_file_handler(filename: str) -> logging.FileHandler:
    handler = logging.FileHandler(LOGS_DIR / filename, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    return handler


def _make_console_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    return handler


# ── Именованные логгеры ─────────────────────────────────────────────────────

def get_app_logger() -> logging.Logger:
    """Логгер для общих событий приложения (запросы, ошибки и т.д.)."""
    logger = logging.getLogger("app")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_make_file_handler("app.log"))
        logger.addHandler(_make_console_handler())
        logger.propagate = False
    return logger


def get_llm_logger() -> logging.Logger:
    """Логгер исключительно для трафика LLM (исходящий запрос и входящий ответ)."""
    logger = logging.getLogger("llm")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_make_file_handler("llm.log"))
        logger.addHandler(_make_console_handler())
        logger.propagate = False
    return logger


# ── Запись трассировки запросов ─────────────────────────────────────────────

_trace_lock = threading.Lock()


def write_request_trace(trace: dict) -> None:
    """Добавляет одну запись JSON-line в logs/requests.log.

    Каждая запись охватывает полный пайплайн для одного запроса пользователя:
      1. user_message       – что спросил пользователь
      2. sql_generation     – вызов LLM, сформировавший SQL-запрос
      3. sql_execution      – запрос, отправленный в БД, и возвращённые строки
      4. chart_generation   – вызов LLM с инжектированными данными из БД
      5. chart_option       – итоговая конфигурация ECharts, отправленная на фронтенд
    """
    line = json.dumps(trace, ensure_ascii=False, default=str) + "\n"
    with _trace_lock:
        with open(LOGS_DIR / "requests.log", "a", encoding="utf-8") as f:
            f.write(line)
