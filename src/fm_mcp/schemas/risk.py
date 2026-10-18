"""Pydantic schemas for risk tools."""
"""Pydantic v2 contracts for risk APIs."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskCreate(BaseModel):
    request_id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=100)
    owner_id: str = Field(min_length=1, max_length=100)
    mitigation_plan: str | None = None
    review_date: date | None = None


class RiskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    owner_id: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = None
    mitigation_plan: str | None = None
    review_date: date | None = None


class RiskAssessmentCreate(BaseModel):
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    risk_score: int | None = Field(default=None, ge=1, le=25)
    assessment_type: str = Field(min_length=1, max_length=30)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_score(self) -> "RiskAssessmentCreate":
        if self.risk_score is not None and self.risk_score != self.likelihood * self.impact:
            raise ValueError("risk_score must match the configured default matrix likelihood × impact")
        return self


class RiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    risk_code: str
    request_id: UUID | None
    title: str
    description: str
    category: str | None
    owner_id: str
    status: str
    mitigation_plan: str | None
    review_date: date | None
    created_by: str
    created_at: datetime
    updated_at: datetime
