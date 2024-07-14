from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from strawberry.extensions.context import (
    ExecutingContextManager,
    OperationContextManager,
    ParsingContextManager,
    ValidationContextManager,
)
from strawberry.utils.await_maybe import await_maybe

from . import SchemaExtension

if TYPE_CHECKING:
    from strawberry.types import ExecutionContext


class SchemaExtensionsRunner:
    extensions: List[SchemaExtension]

    def __init__(
        self,
        execution_context: ExecutionContext,
        extensions: Optional[List[SchemaExtension]] = None,
    ) -> None:
        self.execution_context = execution_context
        self.extensions = extensions if extensions is not None else []

    def operation(self) -> OperationContextManager:
        return OperationContextManager(self.extensions, self.execution_context)

    def validation(self) -> ValidationContextManager:
        return ValidationContextManager(self.extensions, self.execution_context)

    def parsing(self) -> ParsingContextManager:
        return ParsingContextManager(self.extensions, self.execution_context)

    def executing(self) -> ExecutingContextManager:
        return ExecutingContextManager(self.extensions, self.execution_context)

    @classmethod
    def _implments_get_rseults(cls, extension: SchemaExtension) -> bool:
        "Whether the extension implements get_results"
        return type(extension).get_results is not SchemaExtension.get_results

    def get_extensions_results_sync(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for extension in self.extensions:
            if type(self)._implments_get_rseults(extension):
                if inspect.iscoroutinefunction(extension.get_results):
                    msg = "Cannot use async extension hook during sync execution"
                    raise RuntimeError(msg)
                data.update(extension.get_results())  # type: ignore should be sync only...

        return data

    async def get_extensions_results(self, ctx: ExecutionContext) -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        for extension in self.extensions:
            if type(self)._implments_get_rseults(extension):
                data.update(await await_maybe(extension.get_results()))

        data.update(ctx.extensions_results)
        return data
