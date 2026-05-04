"""
Сервис базы данных PostgreSQL.

Предоставляет асинхронный пул соединений и безопасный исполнитель запросов.
Разрешены только SELECT-выражения — весь остальной SQL отклоняется до
обращения к базе данных.
"""

import json
import re
from decimal import Decimal
from datetime import date, datetime
from typing import Any

import asyncpg

from app.config import settings
from app.logger import get_app_logger

log = get_app_logger()

# Регулярное выражение для определения первого значимого SQL-ключевого слова (после удаления комментариев)
_UNSAFE_STMT = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)
_SELECT_START = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

# Удалить однострочные (--) и многострочные (/* */) SQL-комментарии перед проверкой безопасности
_STRIP_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _is_safe_sql(sql: str) -> bool:
    """Вернуть True только если выражение является простым SELECT без DDL/DML."""
    stripped = _STRIP_COMMENTS.sub("", sql).strip()
    if _UNSAFE_STMT.search(stripped):
        return False
    return bool(_SELECT_START.match(stripped))


def _jsonable(value: Any) -> Any:
    """Конвертировать специфичные типы PostgreSQL в JSON-сериализуемые типы Python."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _row_to_dict(record: asyncpg.Record) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in dict(record).items()}


def format_rows_as_text(rows: list[dict[str, Any]]) -> str:
    """
    Форматировать результаты запроса как компактную строку JSON-массива,
    подходящую для передачи в LLM генерации графика в виде блока 'Data:'.
    """
    return json.dumps(rows, ensure_ascii=False)


class DatabaseService:
    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    def is_configured(self) -> bool:
        return bool(settings.DATABASE_URL.strip())

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
        return self._pool

    async def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """
        Выполнить SQL-запрос только на чтение и вернуть результаты как список словарей.

        Вызывает ValueError, если SQL не является SELECT-выражением.
        Вызывает RuntimeError при ошибках базы данных.
        """
        if not _is_safe_sql(sql):
            raise ValueError(
                f"Only SELECT statements are allowed. Rejected SQL: {sql!r}"
            )

        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql)
            result = [_row_to_dict(r) for r in rows]
            log.info(
                "DB query executed",
                extra={"event": "db_query", "rows": len(result), "sql": sql},
            )
            return result
        except asyncpg.PostgresError as exc:
            log.error(
                "DB query failed",
                extra={"event": "db_error", "sql": sql, "error": str(exc)},
            )
            raise RuntimeError(f"Database error: {exc}") from exc

    async def check_status(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "error": "DATABASE_URL not configured"}
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
            return {"ok": True, "version": version}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


db_service = DatabaseService()
