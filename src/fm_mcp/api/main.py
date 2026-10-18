"""FastAPI entry point for the EPIC 3 Workflow Automation API."""

from fastapi import FastAPI

from fm_mcp.api.routers.workflow import router as workflow_router
from fm_mcp.api.routers.approval import router as approval_router
from fm_mcp.api.routers.risk import router as risk_router
from fm_mcp.api.routers.notification import router as notification_router


def create_app() -> FastAPI:
    app = FastAPI(title="FM Workflow Automation API", version="0.1.0")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(risk_router)
    app.include_router(notification_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    import uvicorn
    uvicorn.run("fm_mcp.api.main:app", host="0.0.0.0", port=8000)
