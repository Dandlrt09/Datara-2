"""App-config router: the deployment mode, readable before login (F1 / T1).

UNAUTHENTICATED on purpose: the frontend needs the mode to decide which
screens exist (the email screens are hidden in ``local`` mode) before any
session can exist. It exposes the mode and nothing else.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from server.app_mode import Mode, get_mode

router = APIRouter(prefix="/api/app-config", tags=["app-config"])


class AppConfig(BaseModel):
    mode: Mode


@router.get("", response_model=AppConfig)
def read_app_config() -> AppConfig:
    return AppConfig(mode=get_mode())
