from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ai import analyze_task, build_card, get_mode
from app.ai_quota import reserve_ai_request
from app.api import create_app as create_base_app
from app.auth import require_business
from app.database import Db
from app.models import Participant
from app.schemas import Card
from app.scoring import score_card
from schemas_ai import AnalyzeInput, BuildCardInput


def _validation_error(error: ValueError):
    message = "Тело запроса должно содержать корректный JSON."
    if isinstance(error, ValidationError):
        detail = error.errors()[0]
        field = ".".join(str(part) for part in detail["loc"]) or "запрос"
        context = detail.get("ctx", {})
        messages = {
            "missing": "обязательное поле отсутствует",
            "string_type": "ожидается строка",
            "string_too_short": (
                f"минимум {context.get('min_length')} символов после удаления пробелов"
            ),
            "string_too_long": f"максимум {context.get('max_length')} символов",
            "too_long": f"максимум {context.get('max_length')} элементов",
            "list_type": "ожидается список",
            "literal_error": "недопустимое название поля карточки",
            "extra_forbidden": "неизвестное поле",
        }
        message = f"Поле «{field}»: {messages.get(detail['type'], 'некорректное значение')}."
    return JSONResponse(
        status_code=422, content={"error": {"code": "validation_error", "message": message}}
    )


ai_router = APIRouter(prefix="/api")


@ai_router.get("/health", tags=["system"])
def ai_health():
    return {"status": "ok", "mode": get_mode()}


@ai_router.post("/tasks/analyze", tags=["assistant"])
async def ai_analyze(
    request: Request,
    db: Db,
    business: Annotated[Participant, Depends(require_business)],
):
    try:
        data = AnalyzeInput.model_validate(await request.json())
    except ValueError as error:
        return _validation_error(error)
    reserve_ai_request(db, business.id, request.app.state.settings.ai_daily_limit)
    result = (await run_in_threadpool(analyze_task, data)).model_dump()
    result["score"] = score_card(Card(**result["draft_card"])).model_dump()
    return result


@ai_router.post("/tasks/build-card", tags=["assistant"])
async def ai_build_card(
    request: Request,
    db: Db,
    business: Annotated[Participant, Depends(require_business)],
):
    try:
        data = BuildCardInput.model_validate(await request.json())
    except ValueError as error:
        return _validation_error(error)
    reserve_ai_request(db, business.id, request.app.state.settings.ai_daily_limit)
    return (await run_in_threadpool(build_card, data)).model_dump()


def create_app(settings=None):
    app = create_base_app(settings)
    # Install the three operations before existing routes. Direct APIRoutes work
    # with both flattened and lazily included FastAPI routers.
    app.router.routes[0:0] = list(ai_router.routes)
    return app


app = create_app()
