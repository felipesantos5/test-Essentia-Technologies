from fastapi import APIRouter, Depends, FastAPI

from clinic_api import __version__
from clinic_api.api.deps import require_api_key
from clinic_api.api.routers import health
from clinic_api.errors import register_exception_handlers

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Essentia Clinic API",
        version=__version__,
        description=(
            "Mock REST API with fictitious patients, doctors, schedules, appointments and "
            "payment information. Consumed by the n8n AI attendance workflow. "
            "Every route except `/health` requires the `X-API-Key` header."
        ),
    )
    register_exception_handlers(app)

    protected = APIRouter(dependencies=[Depends(require_api_key)])

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(protected)
    app.include_router(api)
    return app


app = create_app()
