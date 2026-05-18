import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from app.config import settings
from app.logger import get_llm_logger

log = get_llm_logger()


class LLMModelChoice(str, Enum):
    local_qwen25 = "local_qwen25"
    local_qwen35_9b = "local_qwen35_9b"
    local_qwen3_coder_30b = "local_qwen3_coder_30b"
    openrouter_qwen35_27b = "openrouter_qwen35_27b"
    openrouter_gpt4o = "openrouter_gpt4o"
    openrouter_gemini_flash = "openrouter_gemini_flash"
    openrouter_gemini_flash_lite = "openrouter_gemini_flash_lite"
    openrouter_deepseek_v3 = "openrouter_deepseek_v3"


@dataclass(frozen=True)
class LLMRuntime:
    base_url: str
    api_key: str | None
    model: str
    extra_params: dict | None = None


_NO_THINKING = {"thinking": {"type": "disabled"}}

_RUNTIME_TABLE: dict[LLMModelChoice, tuple[str, str, str, dict | None]] = {
    # (base_url_attr, api_key_attr, model_attr, extra_params)
    LLMModelChoice.local_qwen25:              ("LLM_LOCAL_BASE_URL", "LLM_LOCAL_API_KEY", "LLM_LOCAL_MODEL", None),
    LLMModelChoice.local_qwen35_9b:           ("LLM_LOCAL_BASE_URL", "LLM_LOCAL_API_KEY", "LLM_LOCAL_MODEL_QWEN35_9B", None),
    LLMModelChoice.local_qwen3_coder_30b:     ("LLM_LOCAL_BASE_URL", "LLM_LOCAL_API_KEY", "LLM_LOCAL_MODEL_QWEN3_CODER_30B", None),
    LLMModelChoice.openrouter_qwen35_27b:     ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL_QWEN35_27B", None),
    LLMModelChoice.openrouter_gpt4o:          ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL_GPT4O", None),
    LLMModelChoice.openrouter_gemini_flash:   ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL_GEMINI_FLASH", _NO_THINKING),
    LLMModelChoice.openrouter_gemini_flash_lite: ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL_GEMINI_FLASH_LITE", None),
    LLMModelChoice.openrouter_deepseek_v3:       ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL_DEEPSEEK_V3", None),
}


def resolve_llm_runtime(choice: LLMModelChoice) -> LLMRuntime:
    if choice not in _RUNTIME_TABLE:
        raise ValueError(f"Unknown LLM choice: {choice}")
    base_attr, key_attr, model_attr, extra = _RUNTIME_TABLE[choice]
    key = getattr(settings, key_attr).strip()
    return LLMRuntime(
        getattr(settings, base_attr).rstrip("/"),
        key if key else None,
        getattr(settings, model_attr),
        extra_params=extra,
    )


def openrouter_key_configured() -> bool:
    return bool(settings.OPENROUTER_API_KEY.strip())


def requires_openrouter_key(choice: LLMModelChoice) -> bool:
    return choice in (
        LLMModelChoice.openrouter_qwen35_27b,
        LLMModelChoice.openrouter_gpt4o,
        LLMModelChoice.openrouter_gemini_flash,
        LLMModelChoice.openrouter_gemini_flash_lite,
        LLMModelChoice.openrouter_deepseek_v3,
    )


class BaseLLMClient:
    def __init__(self) -> None:
        self._max_retries = settings.LLM_MAX_RETRIES
        self._timeout = settings.LLM_HTTP_TIMEOUT

    async def call_llm(self, messages: list[dict], runtime: LLMRuntime, attempt: int = 0) -> str:
        url = f"{runtime.base_url}/chat/completions"
        payload = {"model": runtime.model, "messages": messages, "temperature": settings.LLM_TEMPERATURE}
        if runtime.extra_params:
            payload.update(runtime.extra_params)

        log.info(
            "LLM request",
            extra={"event": "llm_request", "attempt": attempt, "url": url, "model": runtime.model, "messages": messages},
        )

        t0 = time.perf_counter()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if runtime.api_key:
            headers["Authorization"] = f"Bearer {runtime.api_key}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        content: str = data["choices"][0]["message"]["content"]

        log.info(
            "LLM response",
            extra={
                "event": "llm_response",
                "attempt": attempt,
                "elapsed_ms": elapsed_ms,
                "model": data.get("model", runtime.model),
                "usage": data.get("usage"),
                "content": content,
            },
        )

        return content

    def parse_json(self, raw_text: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        return json.loads(cleaned)

    async def call_llm_json(self, messages: list[dict], runtime: LLMRuntime) -> dict[str, Any]:
        working_messages = list(messages)

        for attempt in range(self._max_retries + 1):
            raw = await self.call_llm(working_messages, runtime, attempt=attempt)
            try:
                return self.parse_json(raw)
            except json.JSONDecodeError:
                if attempt == self._max_retries:
                    log.error(
                        "LLM JSON parse failed after all retries",
                        extra={"event": "llm_json_failed", "attempts": attempt + 1, "last_raw": raw},
                    )
                    raise ValueError(
                        f"LLM did not return valid JSON after {self._max_retries + 1} attempts. "
                        f"Last response: {raw!r}"
                    )
                log.warning(
                    "LLM response was not valid JSON — retrying",
                    extra={"event": "llm_json_retry", "attempt": attempt, "raw": raw},
                )
                working_messages.append({"role": "assistant", "content": raw})
                working_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was not valid JSON. "
                            "Please respond ONLY with a valid JSON object, "
                            "no markdown fences, no explanation."
                        ),
                    }
                )

        raise RuntimeError("Unexpected exit from retry loop")


llm_client = BaseLLMClient()
