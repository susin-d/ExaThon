from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TicketInput(BaseModel):
    source_system: str = Field(min_length=1, max_length=80)
    source_ticket_id: str = Field(min_length=1, max_length=120)
    received_at: datetime
    channel: Literal["branch", "call_centre", "email", "app", "rbi_cms"]
    branch_id: str = Field(min_length=1, max_length=40)
    product: str = Field(min_length=1, max_length=80)
    agent_category: str = Field(min_length=1, max_length=120)
    agent_type: Literal["query", "request", "complaint"]
    resolution: str | None = Field(default=None, max_length=240)
    escalated_to_io: bool = False
    text: str = Field(min_length=3, max_length=20_000)

    @field_validator("source_system", "source_ticket_id", "branch_id", "product")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class BatchInput(BaseModel):
    tickets: list[TicketInput] = Field(min_length=1, max_length=5_000)


class BatchResult(BaseModel):
    accepted: int
    duplicates: int
    queued: int
    ticket_ids: list[str]


class ReviewInput(BaseModel):
    decision: Literal["confirm", "dismiss", "reclassify"]
    reason: str | None = Field(default=None, max_length=1_000)
    corrected_type: Literal["query", "request", "complaint"] | None = None
    corrected_ground: str | None = Field(default=None, max_length=120)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    def validate_semantics(self) -> None:
        if self.decision in {"dismiss", "reclassify"} and not self.reason:
            raise ValueError("A reason is required when dismissing or reclassifying a finding.")
        if self.decision == "reclassify" and not (self.corrected_type or self.corrected_ground):
            raise ValueError("Reclassification requires a corrected type or ground.")
