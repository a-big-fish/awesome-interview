from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiResponseVO(BaseModel, Generic[DataT]):
    code: int = 0
    message: str = "ok"
    data: DataT | None = None
