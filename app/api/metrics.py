# app/api/metrics.py
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, CollectorRegistry
from prometheus_client import multiprocess

router = APIRouter()


@router.get("/metrics")
def metrics():
    registry = CollectorRegistry()
    # Works with or without multiprocess mode
    try:
        multiprocess.MultiProcessCollector(registry)
    except Exception:  # nosec B110
        pass
    data = generate_latest(registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
