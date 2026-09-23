"""Two typed OpenAI agents. They can only return drafts, never mutate application data."""

import asyncio
from functools import lru_cache
from typing import TypeVar

from agents import Agent, ModelSettings, OpenAIResponsesModel, RunConfig, Runner
from agents.exceptions import AgentsException
from fastapi import HTTPException
from openai import (
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.config import ROOT_DIR, Settings
from app.schemas import (
    AnalysisResult,
    AnalyzeRead,
    AnalyzeRequest,
    BuildRead,
    BuildRequest,
    BuildResult,
)

Result = TypeVar("Result", bound=BaseModel)
REVIEW_WARNING = "Проверьте факты и формулировки ИИ перед подтверждением и публикацией."


@lru_cache(maxsize=2)
def instructions(name: str) -> str:
    return (ROOT_DIR / "prompts" / f"{name}.md").read_text(encoding="utf-8")


async def run_agent(
    name: str,
    prompt: str,
    data: AnalyzeRequest,
    output_type: type[Result],
    settings: Settings,
) -> Result:
    key = settings.openai_api_key.get_secret_value().strip()
    if not key:
        raise HTTPException(
            503,
            "OpenAI не настроен: добавьте OPENAI_API_KEY в backend/.env и перезапустите сервер.",
        )

    try:
        async with asyncio.timeout(settings.ai_timeout_seconds):
            async with AsyncOpenAI(
                api_key=key,
                base_url="https://api.openai.com/v1",
                timeout=settings.ai_timeout_seconds,
                max_retries=0,
            ) as client:
                agent = Agent(
                    name=name,
                    instructions=instructions(prompt),
                    model=OpenAIResponsesModel(model=settings.openai_model, openai_client=client),
                    model_settings=ModelSettings(max_tokens=6000, store=False),
                    output_type=output_type,
                )
                result = await Runner.run(
                    agent,
                    input=data.model_dump_json(),
                    max_turns=1,
                    run_config=RunConfig(tracing_disabled=True),
                )
                # Also validate at the application boundary; malformed data never reaches the UI.
                return output_type.model_validate(result.final_output)
    except (TimeoutError, APITimeoutError):
        raise HTTPException(504, "ИИ не ответил вовремя. Попробуйте ещё раз.") from None
    except (AuthenticationError, PermissionDeniedError):
        raise HTTPException(
            503, "Нет доступа к OpenAI. Проверьте API-ключ и доступ проекта к выбранной модели."
        ) from None
    except RateLimitError:
        raise HTTPException(
            429, "Достигнут лимит OpenAI. Проверьте баланс API или повторите запрос позже."
        ) from None
    except (AgentsException, ValidationError):
        raise HTTPException(
            502, "ИИ вернул некорректный ответ. Данные сохранены в форме; повторите запрос."
        ) from None
    except OpenAIError:
        raise HTTPException(
            502, "Не удалось получить ответ OpenAI. Проверьте соединение и настройку модели."
        ) from None


async def analyze_draft(data: AnalyzeRequest, settings: Settings) -> AnalyzeRead:
    result = await run_agent("Draft analyst", "analyze", data, AnalysisResult, settings)
    return AnalyzeRead(**result.model_dump(), mode="openai")


async def build_task_card(data: BuildRequest, settings: Settings) -> BuildRead:
    result = await run_agent("Task card writer", "build_card", data, BuildResult, settings)
    return BuildRead(
        card=result.card,
        warnings=[*result.warnings[:19], REVIEW_WARNING],
        mode="openai",
    )
