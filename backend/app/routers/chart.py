import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.logger import get_app_logger, write_request_trace
from app.prompts.echarts_system import build_system_prompt
from app.prompts.lookup_generation import LOOKUP_GENERATION_PROMPT
from app.prompts.sql_system import SQL_SYSTEM_PROMPT
from app.services.database import db_service, format_rows_as_text
from app.services.llm import (
    LLMModelChoice,
    llm_client,
    openrouter_key_configured,
    requires_openrouter_key,
    resolve_llm_runtime,
)
from app.services.rag import rag_service

router = APIRouter(prefix="/api", tags=["chart"])
log = get_app_logger()


def _unwrap_echarts_root(opt: dict[str, Any]) -> dict[str, Any]:
    if len(opt) != 1:
        return opt
    only = next(iter(opt.values()))
    if not isinstance(only, dict):
        return opt
    key = next(iter(opt.keys()))
    if key in ("chart_option", "option"):
        return only
    return opt


async def _run_lookup_step(
    user_message: str, history: list[dict], runtime: Any
) -> tuple[str, dict]:
    debug: dict = {}
    lookup_messages = [
        {"role": "system", "content": LOOKUP_GENERATION_PROMPT},
        *history[-4:],
        {"role": "user", "content": user_message},
    ]
    debug["prompt"] = lookup_messages

    try:
        llm_response = await llm_client.call_llm_json(lookup_messages, runtime)
        debug["llm_response"] = llm_response
    except Exception as exc:
        log.warning("Lookup generation failed", extra={"event": "lookup_gen_error", "detail": str(exc)})
        debug["error"] = str(exc)
        return "", debug

    lookup_queries: list[str] = llm_response.get("lookup_queries") or []
    debug["lookup_queries"] = lookup_queries

    if not lookup_queries:
        return "", debug

    result_blocks: list[str] = ["━━ LOOKUP RESULTS (use these values in your SQL) ━━"]
    debug["lookup_results"] = []

    for sql in lookup_queries:
        try:
            rows = await db_service.execute_query(sql)
            debug["lookup_results"].append({"query": sql, "rows": rows})
            if rows:
                row_lines = ["  " + str(dict(r)) for r in rows]
                result_blocks.append(f"Query: {sql}")
                result_blocks.append("Results:\n" + "\n".join(row_lines))
        except Exception as exc:
            log.warning("Lookup query failed", extra={"sql": sql, "detail": str(exc)})
            debug["lookup_results"].append({"query": sql, "error": str(exc)})

    context = "\n".join(result_blocks) if len(result_blocks) > 1 else ""
    return context, debug


async def _try_fetch_db_data(
    user_message: str, runtime: Any, history: list[dict] | None = None,
    resolved_context: str = "",
) -> tuple[str | None, dict]:
    trace: dict = {}

    if not db_service.is_configured():
        return None, trace

    system_content = SQL_SYSTEM_PROMPT + ("\n\n" + resolved_context if resolved_context else "")
    sql_messages = [
        {"role": "system", "content": system_content},
        *(history or []),
        {"role": "user", "content": user_message},
    ]
    trace["llm_messages"] = sql_messages

    try:
        sql_response = await llm_client.call_llm_json(sql_messages, runtime)
        trace["llm_response"] = sql_response
    except Exception as exc:
        log.warning(
            "SQL generation failed — falling back to no-DB flow",
            extra={"event": "sql_gen_error", "detail": str(exc)},
        )
        trace["llm_error"] = str(exc)
        return None, trace

    needs_db: bool = bool(sql_response.get("needs_db"))
    sql: str | None = sql_response.get("sql")

    if not needs_db or not sql:
        log.info("SQL agent decided no DB data needed", extra={"event": "sql_not_needed"})
        return None, trace

    log.info("SQL agent generated query", extra={"event": "sql_generated", "sql": sql})
    trace["query"] = sql

    try:
        rows = await db_service.execute_query(sql)
        trace["rows"] = rows
        trace["row_count"] = len(rows)
    except (ValueError, RuntimeError) as exc:
        log.warning(
            "SQL execution failed — falling back to no-DB flow",
            extra={"event": "sql_exec_error", "detail": str(exc)},
        )
        trace["exec_error"] = str(exc)
        return None, trace

    if not rows:
        log.info("SQL query returned no rows", extra={"event": "sql_empty_result"})
        return None, trace

    data_text = format_rows_as_text(rows)
    log.info("DB data fetched for chart generation", extra={"event": "db_data_ready", "rows": len(rows)})
    return data_text, trace


class HistoryMessage(BaseModel):
    role: str
    content: str


class ChartRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = []
    current_chart: dict[str, Any] | None = None
    data_context: str | None = None
    llm_model: LLMModelChoice = LLMModelChoice.local_qwen25


class ChartResponse(BaseModel):
    chart_option: dict
    sql_query: str | None = None
    sql_result: list | None = None
    entity_extraction: dict | None = None
    rag_chunks: list[str] | None = None


@router.post("/chart", response_model=ChartResponse)
async def generate_chart(body: ChartRequest, request: Request) -> ChartResponse:
    log.info(
        "Frontend request received",
        extra={
            "event": "frontend_request",
            "client": request.client.host if request.client else "unknown",
            "prompt": body.message,
            "history_turns": len(body.history),
            "has_current_chart": body.current_chart is not None,
            "has_data_context": body.data_context is not None,
            "llm_model": body.llm_model.value,
        },
    )

    trace: dict = {
        "request_id": uuid.uuid4().hex[:8],
        "ts": datetime.now(timezone.utc).isoformat(),
        "llm_model": body.llm_model.value,
        "step1_user_request": {
            "message": body.message,
            "history_turns": len(body.history),
            "has_current_chart": body.current_chart is not None,
            "has_uploaded_data": body.data_context is not None,
        },
    }

    if requires_openrouter_key(body.llm_model) and not openrouter_key_configured():
        raise HTTPException(
            status_code=400,
            detail="OpenRouter is not configured: set OPENROUTER_API_KEY in backend .env",
        )

    runtime = resolve_llm_runtime(body.llm_model)

    db_data: str | None = None
    sql_trace: dict = {}
    entity_debug: dict = {}
    if not body.data_context:
        history_dicts = [{"role": m.role, "content": m.content} for m in body.history]
        resolved_context, entity_debug = await _run_lookup_step(body.message, history_dicts, runtime)
        if resolved_context:
            db_data, sql_trace = await _try_fetch_db_data(
                body.message, runtime,
                history=history_dicts,
                resolved_context=resolved_context,
            )
        else:
            db_data, sql_trace = None, {}
        if sql_trace:
            trace["step2_sql_generation"] = {
                "llm_messages": sql_trace.get("llm_messages"),
                "llm_response": sql_trace.get("llm_response"),
                "llm_error": sql_trace.get("llm_error"),
            }
            if "query" in sql_trace:
                trace["step3_sql_execution"] = {
                    "query": sql_trace["query"],
                    "row_count": sql_trace.get("row_count"),
                    "rows": sql_trace.get("rows"),
                    "exec_error": sql_trace.get("exec_error"),
                }
    else:
        db_data = None

    def _trace_detail(message: str) -> dict:
        return {
            "message": message,
            "entity_extraction": entity_debug or None,
            "sql_query": sql_trace.get("query"),
            "sql_result": sql_trace.get("rows") or [],
        }

    _MAX_ROWS = 500
    if sql_trace.get("row_count", 0) > _MAX_ROWS:
        raise HTTPException(
            status_code=422,
            detail=_trace_detail(
                f"Запрос вернул {sql_trace['row_count']} строк — слишком много для построения графика (максимум {_MAX_ROWS}). Уточните параметры запроса."
            ),
        )

    if "query" in sql_trace and db_data is None and not body.data_context:
        if sql_trace.get("exec_error"):
            raise HTTPException(
                status_code=502,
                detail=_trace_detail(f"Ошибка базы данных: {sql_trace['exec_error']}"),
            )
        raise HTTPException(
            status_code=404,
            detail=_trace_detail("Нет данных. Проверьте параметры запроса."),
        )

    effective_data_preview = db_data or body.data_context
    if effective_data_preview is None and body.current_chart is None:
        needs_db = (sql_trace.get("llm_response") or {}).get("needs_db", False)
        if needs_db:
            raise HTTPException(
                status_code=404,
                detail=_trace_detail("Не удалось получить данные для построения графика."),
            )

    rag_chunks = await rag_service.retrieve(body.message)

    effective_data = db_data or body.data_context
    has_data = effective_data is not None

    user_content = body.message

    if body.current_chart:
        chart_json = json.dumps(body.current_chart, ensure_ascii=False, indent=2)
        user_content = (
            f"Current ECharts option:\n```json\n{chart_json}\n```\n\n{user_content}"
        )

    if effective_data:
        user_content = f"Data:\n{effective_data}\n\n{user_content}"

    messages: list[dict] = [
        {
            "role": "system",
            "content": build_system_prompt(rag_chunks, has_user_data=has_data),
        },
        *[{"role": m.role, "content": m.content} for m in body.history],
        {"role": "user", "content": user_content},
    ]

    trace["step4_chart_llm_request"] = {"messages": messages}

    try:
        chart_option = _unwrap_echarts_root(
            await llm_client.call_llm_json(messages, runtime)
        )
    except ValueError as exc:
        log.error("Chart generation failed (bad JSON)", extra={"event": "chart_error", "detail": str(exc)})
        trace["step5_chart_option"] = {"error": str(exc)}
        write_request_trace(trace)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Chart generation failed (unexpected)", extra={"event": "chart_error", "detail": str(exc)})
        trace["step5_chart_option"] = {"error": str(exc)}
        write_request_trace(trace)
        raise HTTPException(status_code=500, detail=f"LLM request failed: {exc}") from exc

    trace["step5_chart_option"] = chart_option
    write_request_trace(trace)

    log.info(
        "Chart generation succeeded",
        extra={
            "event": "chart_success",
            "option_keys": list(chart_option.keys()),
            "rag_chunks_used": len(rag_chunks),
            "used_db_data": db_data is not None,
        },
    )
    return ChartResponse(
        chart_option=chart_option,
        sql_query=sql_trace.get("query") if not body.data_context else None,
        sql_result=sql_trace.get("rows") if not body.data_context else None,
        entity_extraction=entity_debug or None,
        rag_chunks=rag_chunks if rag_chunks else None,
    )
