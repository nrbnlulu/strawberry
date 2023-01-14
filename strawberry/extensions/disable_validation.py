from typing import Iterator

from strawberry.extensions.base_extension import Extension


class DisableValidation(Extension):
    """
    Disable query validation

    Example:

    >>> import strawberry
    >>> from strawberry.extensions import DisableValidation
    >>>
    >>> schema = strawberry.Schema(
    ...     Query,
    ...     extensions=[
    ...         DisableValidation,
    ...     ]
    ... )

    """

    def on_operation(self) -> Iterator[None]:
        self.execution_context.validation_rules = ()  # remove all validation_rules
        yield
