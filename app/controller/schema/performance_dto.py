"""Strict numeric-only client performance reports."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.performance import CLIENT_METRICS, NODE_LABELS


class PerformanceSample(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    node: str
    metric: str
    duration: float = Field(ge=0, le=120000)
    status: int = Field(default=200, ge=0, le=599)

    @field_validator("node")
    @classmethod
    def known_node(cls, value):
        if value not in NODE_LABELS:
            raise ValueError("未知性能节点")
        return value

    @field_validator("metric")
    @classmethod
    def known_metric(cls, value):
        if value not in CLIENT_METRICS:
            raise ValueError("未知性能指标")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if 0 < value < 100:
            raise ValueError("状态码无效")
        return value


class PerformanceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    samples: list[PerformanceSample] = Field(min_length=1, max_length=20)
