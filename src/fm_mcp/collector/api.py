"""API nội bộ collector: public DTO cho MCP, private state chỉ dành cho worker."""

import hmac
import os
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .dispatcher import CollectorDispatcher
from .service import CollectorService

service = CollectorService()


def get_service() -> CollectorService:
    return service


ServiceDep = Annotated[CollectorService, Depends(get_service)]


def verify(org_id: str, authorization: str, variable: str):
    expected = os.environ.get(variable, "")
    if not expected or not hmac.compare_digest(authorization.encode(), ("Bearer " + expected).encode()):
        raise HTTPException(401, "Invalid collector credential")
    if org_id != os.environ.get("FM_COLLECTOR_ORG_ID", ""):
        raise HTTPException(403, "Collector tenant binding mismatch")


def operator_auth(org_id: str, authorization: Annotated[str, Header()] = ""):
    verify(org_id, authorization, "FM_COLLECTOR_SERVICE_TOKEN")


def worker_auth(org_id: str, authorization: Annotated[str, Header()] = ""):
    verify(org_id, authorization, "CAPTURE_RUNNER_TOKEN")


@asynccontextmanager
async def lifespan(_app):
    required = ("FM_COLLECTOR_ORG_ID", "FM_COLLECTOR_SERVICE_TOKEN", "FM_COLLECTOR_CONTEXT_TOKEN", "CAPTURE_RUNNER_TOKEN")
    if not all(os.environ.get(name) for name in required):
        raise RuntimeError("Collector tenant binding and service credentials must be configured")
    service.migrate()
    dispatcher = CollectorDispatcher(service)
    dispatcher.start()
    try:
        yield
    finally:
        dispatcher.close()


app = FastAPI(title="FM Collector Orchestration Service", lifespan=lifespan)
public = APIRouter(prefix="/internal/tenants/{org_id}", dependencies=[Depends(operator_auth)])
worker = APIRouter(prefix="/internal/worker/{org_id}", dependencies=[Depends(worker_auth)])


@app.exception_handler(ValueError)
async def conflict(_request, _error):
    return JSONResponse(status_code=409, content={"detail": "Collector không chấp nhận trạng thái hoặc cấu hình hiện tại"})


@app.exception_handler(LookupError)
async def missing(_request, _error):
    return JSONResponse(status_code=404, content={"detail": "Không tìm thấy lượt chạy collector"})


@app.exception_handler(httpx.HTTPError)
async def unavailable(_request, error):
    status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else 503
    if status not in (400, 404, 409, 422):
        status = 503
    return JSONResponse(status_code=status, content={"detail": "Không đọc được nguồn hoặc runtime collector; kiểm tra cấu hình"})


class SyncInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class BeginInput(BaseModel):
    name: str = Field(pattern=r"^[a-z_]+$")
    attempt: int = Field(ge=1, le=100000)


class PulseInput(BaseModel):
    name: str
    token: str = Field(pattern=r"^[0-9a-f]{32}$")
    progress: dict = Field(default_factory=dict)


class FinishInput(BaseModel):
    step: dict
    output: dict = Field(default_factory=dict)
    error_code: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,100}$")


@public.get("/health")
def health(org_id: str, svc: ServiceDep) -> dict:
    return {"status": "ok", "scheduler_ready": svc.scheduler.ready(), "execution_backend": "airflow"}


@public.post("/connections/{connection_id}/sync", status_code=202)
def sync(org_id: str, connection_id: str, body: SyncInput, svc: ServiceDep) -> dict:
    return svc.sync(org_id, connection_id, body.request_key)


@public.get("/connections/{connection_id}/capture/status")
def status(org_id: str, connection_id: str, svc: ServiceDep) -> dict:
    return svc.status(org_id, connection_id)


@public.get("/connections/{connection_id}/capture/jobs")
def history(org_id: str, connection_id: str, svc: ServiceDep, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict:
    return svc.history(org_id, connection_id, limit)


@public.post("/connections/{connection_id}/capture/cancel", status_code=202)
def cancel_source(org_id: str, connection_id: str, svc: ServiceDep) -> dict:
    return svc.cancel(org_id, connection_id)


@public.post("/connections/{connection_id}/sync/retry", status_code=202)
def retry_source(org_id: str, connection_id: str, svc: ServiceDep) -> dict:
    svc.retry(org_id, connection_id)
    return svc.status(org_id, connection_id)["job"]


@public.post("/connections/{connection_id}/test")
def test_source(org_id: str, connection_id: str, svc: ServiceDep) -> dict:
    context, _ = svc.source(org_id, connection_id, snapshot=True)
    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.post(os.environ.get("CAPTURE_RUNNER_URL", "http://capture-runner:8020") + "/sources/test",
                               headers={"Authorization": "Bearer " + os.environ.get("CAPTURE_RUNNER_TOKEN", "")},
                               json={"connector": context["connector"], "config": context["config"]})
        response.raise_for_status()
        return response.json()


@public.get("/pipelines")
def list_runs(org_id: str, svc: ServiceDep, connection: str = "", status: str = "",
              offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict:
    return svc.repository.list(org_id, connection=connection, status=status, offset=offset, limit=limit)


@public.get("/pipelines/{identity}")
def detail(org_id: str, identity: str, svc: ServiceDep) -> dict:
    return svc.repository.get(org_id, identity)


@public.get("/pipelines/{identity}/events")
def events(org_id: str, identity: str, svc: ServiceDep, after: Annotated[int, Query(ge=0)] = 0) -> dict:
    return {"items": svc.repository.events(org_id, identity, after)}


@public.post("/pipelines/{identity}/cancel", status_code=202)
def cancel_run(org_id: str, identity: str, svc: ServiceDep) -> dict:
    return svc.cancel_run(org_id, identity)


@public.post("/pipelines/{identity}/retry", status_code=202)
def retry_run(org_id: str, identity: str, svc: ServiceDep) -> dict:
    run = svc.repository.get(org_id, identity)
    return svc.retry(org_id, run["connection_id"], identity)


@worker.get("/runs/{identity}")
def private_run(org_id: str, identity: str, svc: ServiceDep) -> dict:
    return svc.repository.get(org_id, identity, private=True)


@worker.post("/runs/{identity}/begin")
def begin(org_id: str, identity: str, body: BeginInput, svc: ServiceDep) -> dict:
    return svc.repository.begin(org_id, identity, body.name, body.attempt)


@worker.post("/runs/{identity}/pulse")
def pulse(org_id: str, identity: str, body: PulseInput, svc: ServiceDep) -> dict:
    svc.repository.get(org_id, identity)
    return {"valid": svc.repository.pulse(identity, body.name, body.token, body.progress)}


@worker.post("/runs/{identity}/finish")
def finish(org_id: str, identity: str, body: FinishInput, svc: ServiceDep) -> dict:
    svc.repository.get(org_id, identity)
    svc.repository.finish_step(identity, body.step, output=body.output, error_code=body.error_code)
    return {"ok": True}


@worker.get("/runs/{identity}/output/{name}")
def output(org_id: str, identity: str, name: str, svc: ServiceDep) -> dict:
    svc.repository.get(org_id, identity)
    return svc.repository.output(identity, name)


@worker.post("/runs/{identity}/complete")
def complete(org_id: str, identity: str, svc: ServiceDep) -> dict:
    return {"status": svc.repository.complete(org_id, identity)}


@worker.post("/runs/{identity}/cancel")
def worker_cancel(org_id: str, identity: str, svc: ServiceDep) -> dict:
    svc.repository.cancel(org_id, identity)
    return {"ok": True}


app.include_router(public)
app.include_router(worker)


def main():
    import uvicorn
    uvicorn.run("fm_mcp.collector.api:app", host="0.0.0.0", port=8021)
