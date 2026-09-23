from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ai import analyze_task, build_card, get_mode
from app.api import create_app
from schemas_ai import AnalyzeInput, BuildCardInput

app = create_app()


def _validation_error(error: ValidationError):
    message = error.errors()[0].get("msg", "Некорректный вход")
    return JSONResponse(
        status_code=422, content={"error": {"code": "validation_error", "message": message}}
    )


ai_router = APIRouter(prefix="/api")


@ai_router.get("/health", tags=["system"])
def ai_health():
    return {"status": "ok", "mode": get_mode()}


@ai_router.post("/tasks/analyze", tags=["assistant"])
async def ai_analyze(request: Request):
    try:
        data = AnalyzeInput.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        if isinstance(error, ValidationError):
            return _validation_error(error)
        return JSONResponse(
            status_code=422, content={"error": {"code": "validation_error", "message": str(error)}}
        )
    return (await analyze_task(data)).model_dump()


@ai_router.post("/tasks/build-card", tags=["assistant"])
async def ai_build_card(request: Request):
    try:
        data = BuildCardInput.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        if isinstance(error, ValidationError):
            return _validation_error(error)
        return JSONResponse(
            status_code=422, content={"error": {"code": "validation_error", "message": str(error)}}
        )
    return (await build_card(data)).model_dump()


app.include_router(ai_router)
ai_routes = app.router.routes[-3:]
del app.router.routes[-3:]
app.router.routes[0:0] = ai_routes
