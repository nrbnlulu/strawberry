from __future__ import annotations

from typing import Any, Dict, TypeVar

from pydantic import BaseModel
from typing_extensions import Protocol

from strawberry.types.types import StrawberryDefinition


PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class StrawberryTypeFromPydantic(Protocol[PydanticModel]):
    """This class does not exist in runtime.
    It only makes the methods below visible for IDEs"""

    def __init__(self, **kwargs):
        ...

    @staticmethod
    def from_pydantic(
        instance: PydanticModel, extra: Dict[str, Any] = None
    ) -> StrawberryTypeFromPydantic[PydanticModel]:
        ...

    def to_pydantic(self, **kwargs) -> PydanticModel:
        ...

    @property
    def __strawberry_definition__(self) -> StrawberryDefinition:
        ...

    @property
    def _pydantic_type(self) -> PydanticModel:
        ...
