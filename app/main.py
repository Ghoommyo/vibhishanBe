from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.routers import auth, dev, health, notifications, requests, users


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Vibishan API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(users.router)
    api.include_router(requests.router)
    api.include_router(notifications.router)
    if settings.enable_dev_endpoints:
        api.include_router(dev.router)
    app.include_router(api)
    return app


app = create_app()
