from dataclasses import dataclass
from random import choice

from fastapi import Header

from .settings import get_settings


@dataclass(frozen=True)
class ActorContext:
    actor_id: str
    role: str = "internal_ombudsman"


def get_actor(x_actor_id: str | None = Header(default=None)) -> ActorContext:
    """Phase-one identity seam. Replace with verified OIDC claims, not feature rewrites."""
    settings = get_settings()
    return ActorContext(actor_id=x_actor_id or choice(settings.demo_user_ids))
