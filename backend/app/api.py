from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from app import auth, routes
from app.config import ROOT_DIR, Settings
from app.database import Db, create_db_engine
from app.leaderboard import router as profiles_router


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM tasks LIMIT 1"))
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="GhostTech API",
        version="0.2.0",
        lifespan=lifespan,
        description="Бизнес-задачи, рейтинг, команды, отклики и этапы работы.",
    )
    app.state.settings, app.state.engine = settings, engine

    @app.middleware("http")
    async def validate_api_request(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {
            "POST",
            "PATCH",
            "PUT",
            "DELETE",
        }:
            origin = request.headers.get("origin")
            same_origin = f"{request.url.scheme}://{request.url.netloc}"
            allowed_origins = {
                same_origin,
                *(value.rstrip("/") for value in settings.frontend_origins),
            }
            if origin is not None and origin not in allowed_origins:
                return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})

            expects_json = request.method in {"POST", "PATCH", "PUT"} and not (
                request.method == "POST" and request.url.path == "/api/auth/logout"
            )
            if expects_json:
                content_type = (
                    request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                is_json = content_type == "application/json" or (
                    content_type.startswith("application/") and content_type.endswith("+json")
                )
                if not is_json:
                    return JSONResponse(
                        status_code=415, content={"detail": "JSON Content-Type is required"}
                    )

        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def disable_api_cache(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["system"])
    def health(db: Db):
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": engine.dialect.name,
            "mode": settings.assistant_mode,
            "ai_configured": bool(settings.openai_api_key.get_secret_value().strip()),
        }

    api.include_router(auth.router)
    api.include_router(routes.router)
    api.include_router(profiles_router)
    app.include_router(api)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT_DIR / "frontend/index.html")

    @app.get("/{asset}", include_in_schema=False)
    @app.get("/static/{asset}", include_in_schema=False)
    def static_asset(asset: str):
        if asset not in {"styles.css", "app.js", "api.js", "mock.js"}:
            raise HTTPException(404)
        return FileResponse(ROOT_DIR / "frontend" / asset)

    return app
