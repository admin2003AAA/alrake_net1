"""
API router: aggregates all endpoint routers.
"""
from fastapi import APIRouter

from app.api import alerts, devices, discovery, health, topology

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(devices.router)
api_router.include_router(alerts.router)
api_router.include_router(discovery.router)
api_router.include_router(topology.router)
