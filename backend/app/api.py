from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app import routes
from app.config import ROOT_DIR, Settings
from app.database import Db, create_db_engine


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def disable_api_cache(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["system"])
    def health(db: Db):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": engine.dialect.name, "mode": "demo"}

    api.include_router(routes.router)
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
