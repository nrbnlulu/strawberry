from __future__ import annotations

from abc import ABC, abstractmethod
from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    Mapping,
    Type,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from typing_extensions import TypeGuard

    from strawberry.types.types import WithTypeDefinition


class StrawberryType(ABC):
    @cached_property
    def has_type_definition(
        self,
    ) -> Callable[[Any], TypeGuard[Type[WithTypeDefinition]]]:
        from .types.types import has_type_definition

        return has_type_definition

    @property
    def type_params(self) -> List[TypeVar]:
        return []

    @abstractmethod
    def copy_with(
        self, type_var_map: Mapping[TypeVar, Union[StrawberryType, type]]
    ) -> Union[StrawberryType, type]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def is_generic(self) -> bool:
        raise NotImplementedError()

    def has_generic(self, type_var: TypeVar) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        from strawberry.annotation import StrawberryAnnotation

        if isinstance(other, StrawberryType):
            return self is other

        elif isinstance(other, StrawberryAnnotation):
            return self == other.resolve()

        else:
            # This could be simplified if StrawberryAnnotation.resolve() always returned
            # a StrawberryType
            resolved = StrawberryAnnotation(other).resolve()
            if isinstance(resolved, StrawberryType):
                return self == resolved
            else:
                return NotImplemented

    def __hash__(self) -> int:
        # TODO: Is this a bad idea? __eq__ objects are supposed to have the same hash
        return id(self)


class StrawberryContainer(StrawberryType):
    def __init__(self, of_type: Union[StrawberryType, type]):
        self.of_type = of_type

    def __hash__(self) -> int:
        return hash((self.__class__, self.of_type))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StrawberryType):
            if isinstance(other, StrawberryContainer):
                return self.of_type == other.of_type
            else:
                return False

        return super().__eq__(other)

    @property
    def type_params(self) -> List[TypeVar]:
        if self.has_type_definition(self.of_type):
            parameters = getattr(self.of_type, "__parameters__", None)

            return list(parameters) if parameters else []

        elif isinstance(self.of_type, StrawberryType):
            return self.of_type.type_params

        else:
            return []

    def copy_with(
        self, type_var_map: Mapping[TypeVar, Union[StrawberryType, type]]
    ) -> StrawberryType:
        of_type_copy: Union[StrawberryType, type] = self.of_type

        # TODO: Obsolete with StrawberryObject
        if self.has_type_definition(self.of_type):
            type_definition = self.of_type.__strawberry_definition__

            if type_definition.is_generic:
                of_type_copy = type_definition.copy_with(type_var_map)

        elif isinstance(self.of_type, StrawberryType) and self.of_type.is_generic:
            of_type_copy = self.of_type.copy_with(type_var_map)

        return type(self)(of_type_copy)

    @property
    def is_generic(self) -> bool:
        # TODO: Obsolete with StrawberryObject
        type_ = self.of_type
        if self.has_type_definition(self.of_type):
            type_ = self.of_type.__strawberry_definition__

        if isinstance(type_, StrawberryType):
            return type_.is_generic

        return False

    def has_generic(self, type_var: TypeVar) -> bool:
        if isinstance(self.of_type, StrawberryType):
            return self.of_type.has_generic(type_var)
        return False


class StrawberryList(StrawberryContainer):
    ...


class StrawberryOptional(StrawberryContainer):
    ...


class StrawberryTypeVar(StrawberryType):
    def __init__(self, type_var: TypeVar):
        self.type_var = type_var

    def copy_with(
        self, type_var_map: Mapping[TypeVar, Union[StrawberryType, type]]
    ) -> Union[StrawberryType, type]:
        return type_var_map[self.type_var]

    @property
    def is_generic(self) -> bool:
        return True

    def has_generic(self, type_var: TypeVar) -> bool:
        return self.type_var == type_var

    @property
    def type_params(self) -> List[TypeVar]:
        return [self.type_var]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StrawberryTypeVar):
            return self.type_var == other.type_var
        if isinstance(other, TypeVar):
            return self.type_var == other

        return super().__eq__(other)

    def __hash__(self):
        return hash(self.type_var)
