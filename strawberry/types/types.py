from __future__ import annotations

import dataclasses
import types
import typing
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from strawberry.exceptions import MissingFieldAnnotationError
from strawberry.private import is_private
from strawberry.type import StrawberryType
from strawberry.utils.str_converters import to_camel_case
from strawberry.utils.typing import is_generic as is_type_generic


if TYPE_CHECKING:
    from graphql import GraphQLResolveInfo

    from strawberry.field import StrawberryField

T = TypeVar("T")


def _get_interfaces(cls: Type[T]) -> List[TypeDefinition]:
    interfaces = []

    for base in cls.__bases__:
        if type_definition := get_type_definition(base):
            if type_definition.is_interface:
                interfaces.append(type_definition)

        for inherited_interface in _get_interfaces(base):
            interfaces.append(inherited_interface)

    return interfaces


def _get_fields(cls: Type) -> List["StrawberryField"]:
    """Get all the strawberry fields off a strawberry.type cls

    This function returns a list of StrawberryFields (one for each field item), while
    also paying attention the name and typing of the field.

    StrawberryFields can be defined on a strawberry.type class as either a dataclass-
    style field or using strawberry.field as a decorator.

    >>> import strawberry
    >>> @strawberry.type
    ... class Query:
    ...     type_1a: int = 5
    ...     type_1b: int = strawberry.field(...)
    ...     type_1c: int = strawberry.field(resolver=...)
    ...
    ...     @strawberry.field
    ...     def type_2(self) -> int:
    ...         ...

    Type #1:
        A pure dataclass-style field. Will not have a StrawberryField; one will need to
        be created in this function. Type annotation is required.

    Type #2:
        A field defined using @strawberry.field as a decorator around the resolver. The
        resolver must be type-annotated.

    The StrawberryField.python_name value will be assigned to the field's name on the
    class if one is not set by either using an explicit strawberry.field(name=...) or by
    passing a named function (i.e. not an anonymous lambda) to strawberry.field
    (typically as a decorator).
    """
    # Deferred import to avoid import cycles
    from strawberry.field import StrawberryField

    fields: Dict[str, StrawberryField] = {}

    # TODO: What is this?
    # Find the class that each field was originally defined in, so we can use
    # that scope later when resolving the type, as it may have different names
    # available to it.
    origins: Dict[str, type] = {field_name: cls for field_name in cls.__annotations__}

    for base in cls.__mro__:
        if _type_definition := get_type_definition(base):
            for field in _type_definition.fields:
                if field.python_name in base.__annotations__:
                    origins.setdefault(field.python_name, base)

    return list(fields.values())


def get_type_definition(
    type_: Any,
) -> Optional[Union[TypeDefinition, TemplateTypeDefinition]]:
    origin = type_
    # generics store their class in __origin__
    if origin_ := getattr(type_, "__origin__", False):
        origin = origin_
    res = getattr(origin, "_type_definition", None)
    if isinstance(res, TypeDefinition):
        return res
    else:
        return None


template__type_definitions: Dict[str, "TemplateTypeDefinition"] = {}


@dataclasses.dataclass(eq=False)
class TypeDefinition(StrawberryType):
    name: str
    is_input: bool
    is_interface: bool
    origin: Type
    description: Optional[str]
    interfaces: List["TypeDefinition"]
    extend: bool
    directives: Optional[Sequence[object]]
    is_type_of: Optional[Callable[[Any, GraphQLResolveInfo], bool]]
    fields: List["StrawberryField"]
    # fields for generics.
    concrete_of: Optional["TemplateTypeDefinition"] = None
    """Concrete implementations of Generic TypeDefinitions fill this in"""
    type_var_map: Mapping[TypeVar, Union[StrawberryType, type]] = dataclasses.field(
        default_factory=dict
    )
    signature: Optional[int] = None
    # generics names are changed by strawberry.
    graphql_name: str = None

    @classmethod
    def from_class(
        cls,
        origin: Type,
        name: Optional[str] = None,
        is_input: bool = False,
        is_interface: bool = False,
        description: Optional[str] = None,
        directives: Optional[Sequence[object]] = (),
        extend: bool = False,
    ) -> Union["TypeDefinition", "TemplateTypeDefinition"]:
        # at this point all the strawberry fields in the class are
        # without an origin and a python name.
        from strawberry.field import StrawberryField

        name = name or to_camel_case(origin.__name__)
        strawberry_fields: Dict[str, StrawberryField] = {}

        # find fields in parents.
        for base in origin.__bases__:
            if _type_definition := get_type_definition(base):
                if isinstance(_type_definition, TemplateTypeDefinition):
                    base_annots = base.__annotations__.copy()
                    base_annots.update(origin.__annotations__)
                    origin.__annotations__.update(base_annots)
                for field in _type_definition.fields:
                    assert field.python_name
                    strawberry_fields[field.python_name] = field

        # find fields in this class.
        for field_name, field_ in [field for field in list(origin.__dict__.items())]:
            if not isinstance(field_, (StrawberryField, dataclasses.Field)):
                # Not a dataclasses.Field, nor a StrawberryLazyField. Ignore
                continue

            if isinstance(field_, dataclasses.Field):
                # If somehow a non-StrawberryField field is added to
                # the cls without annotations
                # it raises an exception.
                # This would occur if someone manually uses `dataclasses.field`
                # This is similar to the check that dataclasses do during creation,
                # https://github.com/python/cpython/blob/6fed3c85402c5ca704eb3f3189ca3f5c67a08d19/Lib/dataclasses.py#L881-L884,
                if field_name not in origin.__annotations__:
                    # Field object exists but did not get an annotation
                    raise MissingFieldAnnotationError(field_name)

            # set name and origin for the field.
            if isinstance(field_, StrawberryField):
                field_.python_name = field_name
                field_ = field_(origin)
                strawberry_fields[field_.python_name] = field_

            # inject the dataclass strawberry fields we got so far.
            for sb_field in strawberry_fields.values():
                origin.__annotations__[
                    sb_field.python_name
                ] = sb_field.type_annotation.safe_resolve()
                setattr(origin, sb_field.python_name, sb_field.to_dataclass_field())

        #  we can now create the dataclass
        origin = dataclasses.dataclass(origin)

        # Create a StrawberryField for fields that didn't use strawberry.field
        for field in dataclasses.fields(origin):
            if field.name not in strawberry_fields:
                # Only ignore Private fields that weren't defined using StrawberryFields
                if is_private(field.type):
                    continue

                _strawberry_field = StrawberryField.from_dataclasses_field(
                    origin=origin, dataclasses_field=field
                )
                strawberry_fields[_strawberry_field.python_name] = _strawberry_field

        # find interfaces
        interfaces = _get_interfaces(origin)
        fetched_fields = list(strawberry_fields.values())

        # dataclasses removes attributes from the class here:
        # https://github.com/python/cpython/blob/577d7c4e/Lib/dataclasses.py#L873-L880
        # so we need to restore them, this will change in the future, but for now this
        # solution should suffice
        for field_ in fetched_fields:
            if field_.base_resolver and field_.python_name:
                wrapped_func = field_.base_resolver.wrapped_func

                # Bind the functions to the class object. This is necessary because when
                # the @strawberry.field decorator is used on @staticmethod/@classmethods,
                # we get the raw staticmethod/classmethod objects before class evaluation
                # binds them to the class. We need to do this manually.
                if isinstance(wrapped_func, staticmethod):
                    bound_method = wrapped_func.__get__(origin)
                    field_.base_resolver.wrapped_func = bound_method
                elif isinstance(wrapped_func, classmethod):
                    bound_method = types.MethodType(wrapped_func.__func__, origin)
                    field_.base_resolver.wrapped_func = bound_method

                setattr(origin, field_.python_name, wrapped_func)

        is_type_of = getattr(origin, "is_type_of", None)

        ret = cls(
            name=name,
            origin=origin,
            is_input=is_input,
            is_interface=is_interface,
            description=description,
            directives=directives,
            extend=extend,
            interfaces=interfaces,
            fields=fetched_fields,
            is_type_of=is_type_of,
        )
        if is_type_generic(ret.origin):
            ret = TemplateTypeDefinition.from_class(
                origin=origin,
                name=name or origin.__name__,
                is_input=is_input,
                is_interface=is_interface,
                description=description,
                directives=directives,
                extend=extend,
                interfaces=[],
                is_type_of=None,
                fields=[],
            )
            template__type_definitions[ret.name] = ret
        return ret

    def get_field_by_name(self, name: str) -> "StrawberryField":
        for field in self.fields:
            if field.python_name == name:
                return field
        raise NameError(f"field <{name}> not found")

    @property
    def is_generic(self) -> Optional[TemplateTypeDefinition]:
        # good for typing and reducing import cycles.
        if isinstance(self, TemplateTypeDefinition):
            return self
        return None

    # TODO: replace with StrawberryObject
    def validate(self, instance: type) -> bool:
        for field in dataclasses.fields(instance):
            this_field = self.get_field_by_name(field.name)
            value = getattr(instance, field.name)
            if not this_field.validate(value):
                return False
        return True


@dataclasses.dataclass(eq=False)
class TemplateTypeDefinition(TypeDefinition):
    # generic type vars:
    parameters: Tuple[TypeVar] = None
    # not used here
    concrete_of = None
    # TODO: replace with `StrawberryObject`
    implementations: Dict[int, type] = dataclasses.field(default_factory=dict)
    generic_fields: List[StrawberryField] = dataclasses.field(default_factory=list)
    graphql_name: None = dataclasses.field(init=False)

    @classmethod
    def from_class(cls, /, origin: type, **kwargs) -> "TemplateTypeDefinition":
        params = getattr(origin, "__parameters__", None)
        assert isinstance(params, tuple)
        return cls(parameters=params, origin=origin, **kwargs)

    # TODO: return `StrawberryObject`
    def generate(self, passed_types: tuple) -> type:
        """
        this method will recursively generate TypeDefinition instances from
        template classes trying to stick to the public API
        and leave generation to strawberry.
        :param passed_types: tuple of __args__ from the generic alias.
        """
        from strawberry.field import StrawberryField, resolveable

        signature = hash(passed_types)
        if cached := self.implementations.get(signature, None):
            return cached
        type_var_map = dict(zip(self.parameters, passed_types))
        new_type = type(self.name, self.origin.__bases__, dict(self.origin.__dict__))
        # parameters must not be copied, since it is no longer a template class.
        new_type.__parameters__ = None

        fields = new_type.__annotations__.copy()
        fields.update(new_type.__dict__.copy())
        new_class_annotations = {}
        new_fields = {}
        # find field type in annotations.
        for name, field in fields.items():
            # pre-evaluation of fields for some checks we'll do soon.
            if isinstance(field, StrawberryField):
                field.python_name = name
                field = field(new_type)
                field_type = field.type
            elif field_type := new_type.__annotations__.get(name, None):
                resolver = resolveable(getattr(new_type, name, None))
                field = StrawberryField(
                    origin=new_type, python_name=name, base_resolver=resolver
                )
            else:
                continue

            # find the type var or generate a new type.
            field_type = _resolve_field_type(field_type, field, type_var_map)

            new_class_annotations[name] = field_type
            # for basic fields we just need to update the class annotation.
            if not field.is_basic_field:
                f = field.base_resolver.wrapped_func
                f.__annotations__["return"] = field_type
                # evolve resolver.
                new_fields[name] = field(f)

        # inject evaluated annotations and fields.
        new_type.__annotations__ = new_class_annotations
        for name, field in new_fields.items():
            setattr(new_type, name, field)

        _type_definition = TypeDefinition.from_class(
            new_type,
            self.name,
            is_input=self.is_input,
            is_interface=self.is_interface,
            directives=self.directives,
            description=self.description,
            extend=self.extend,
        )
        _type_definition.signature = signature
        _type_definition.type_var_map = type_var_map
        _type_definition.concrete_of = self
        new_type._type_definition = _type_definition
        self.implementations[signature] = new_type
        return new_type


def _resolve_field_type(
    field_type: Any, field: StrawberryField, type_var_map: Mapping[TypeVar, Any]
):
    """recursive function finding the field type"""
    if strawberry_definition := get_type_definition(field_type):
        if isinstance(strawberry_definition, TemplateTypeDefinition):
            args = typing.get_args(field_type)
            assert isinstance(args, tuple)
            child_args = tuple(type_var_map[arg] for arg in args if arg in type_var_map)
            return strawberry_definition.generate(child_args)

    elif isinstance(field_type, StrawberryType):
        if type_var := getattr(field_type, "type_var", None):
            return type_var_map[type_var]
        elif of_type := getattr(field_type, "of_type", None):
            if type_var := getattr(of_type, "type_var", None):
                field_type.of_type = type_var_map[type_var]
                return field_type
            return _resolve_field_type(
                field.type_annotation.annotation, of_type, type_var_map
            )

    elif isinstance(field_type, TypeVar):
        return type_var_map[field_type]

    # handle Optional, List, and other Generic aliases.
    elif origin := typing.get_origin(field_type):
        res = []
        for arg in typing.get_args(field_type):
            res.append(_resolve_field_type(arg, field, type_var_map))
        return origin[tuple(res)]

    return field_type
