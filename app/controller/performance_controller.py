"""Authenticated, best-effort ingestion; reading stays in the admin controller."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ValidationError

from app.controller.schema.performance_dto import PerformanceBatch

router = APIRouter(prefix="/my-schedule/telemetry", tags=["performance"])


@router.post("", status_code=204)
async def collect(request: Request):
    service = request.app.state.performance
    if not service.enabled:
        return Response(status_code=204)
    if not request.app.state.auth_service.limiter.allow(
        f"performance:{request.state.user.id}", 30, timedelta(minutes=1)
    ):
        raise HTTPException(status_code=429, detail="上报过于频繁", headers={"Retry-After": "60"})
    form = await request.form()
    payload = str(form.get("payload", ""))
    if len(payload.encode("utf-8")) > 12000:
        raise HTTPException(status_code=413, detail="性能批次过大")
    try:
        batch = PerformanceBatch.model_validate_json(payload)
    except ValidationError as exc:
        # Validation details may echo client input. Return only a fixed message.
        raise HTTPException(status_code=422, detail="性能样本格式无效") from exc
    for sample in batch.samples:
        service.record(sample.node, "browser", sample.metric, sample.duration, sample.status)
    return Response(status_code=204)
