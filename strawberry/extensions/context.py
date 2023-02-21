from __future__ import annotations

import contextlib
import inspect
import warnings
from asyncio import iscoroutinefunction
from typing import (
    TYPE_CHECKING,
    AsyncIterator,
    Callable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Union,
    no_type_check,
)

from strawberry.extensions import Extension
from strawberry.utils.await_maybe import AwaitableOrValue, await_maybe

if TYPE_CHECKING:
    from strawberry.extensions.base_extension import Hook


class WrappedHook(NamedTuple):
    extension: Extension
    initialized_hook: Union[AsyncIterator[None], Iterator[None]]
    is_async: bool


class ExtensionContextManagerBase:
    __slots__ = ("hooks", "deprecation_message", "default_hook")

    def __init_subclass__(cls):
        cls.DEPRECATION_MESSAGE = (
            f"Event driven styled extensions for "
            f"{cls.LEGACY_ENTER} or {cls.LEGACY_EXIT}"
            f" are deprecated, use {cls.HOOK_NAME} instead"
        )

    HOOK_NAME: str
    DEPRECATION_MESSAGE: str
    LEGACY_ENTER: str
    LEGACY_EXIT: str

    def __init__(self, extensions: List[Extension]):
        self.hooks: List[WrappedHook] = []
        self.default_hook: Hook = getattr(Extension, self.HOOK_NAME)
        for extension in extensions:
            hook = self.get_hook(extension)
            if hook:
                self.hooks.append(hook)

    def get_hook(self, extension: Extension) -> Optional[WrappedHook]:
        on_start = getattr(extension, self.LEGACY_ENTER, None)
        on_end = getattr(extension, self.LEGACY_EXIT, None)

        is_legacy = on_start is not None or on_end is not None
        hook_fn: Optional[Hook] = getattr(type(extension), self.HOOK_NAME)
        hook_fn = hook_fn if hook_fn is not self.default_hook else None
        if is_legacy and hook_fn is not None:
            raise RuntimeError(
                f"{Extension} defines both legacy and new style extension hooks for "
                "{self.HOOK_NAME}"
            )
        elif is_legacy:
            warnings.warn(self.DEPRECATION_MESSAGE, DeprecationWarning)
            return self.from_legacy(extension, on_start, on_end)

        if hook_fn:
            if inspect.isgeneratorfunction(hook_fn):
                return WrappedHook(extension, hook_fn(extension), False)

            elif inspect.isasyncgenfunction(hook_fn):
                return WrappedHook(extension, hook_fn(extension), True)

            elif callable(hook_fn):
                return self.from_callable(extension, hook_fn)

        return None  # Current extension does not define a hook for this lifecycle stage

    @staticmethod
    def from_legacy(
        extension: Extension,
        on_start: Optional[Callable[[], None]] = None,
        on_end: Optional[Callable[[], None]] = None,
    ) -> WrappedHook:
        if iscoroutinefunction(on_start) or iscoroutinefunction(on_end):

            async def iterator():
                if on_start:
                    await await_maybe(on_start())
                yield
                if on_end:
                    await await_maybe(on_end())

            hook = iterator()
            return WrappedHook(extension, hook, True)

        else:

            def iterator():
                if on_start:
                    on_start()
                yield
                if on_end:
                    on_end()

            hook = iterator()
            return WrappedHook(extension, hook, False)

    @staticmethod
    def from_callable(
        extension: Extension,
        func: Callable[[Extension], AwaitableOrValue],
    ) -> WrappedHook:
        if iscoroutinefunction(func):

            async def iterator():
                await func(extension)
                yield

            hook = iterator()
            return WrappedHook(extension, hook, True)
        else:

            def iterator():
                func(extension)
                yield

            hook = iterator()
            return WrappedHook(extension, hook, False)

    @no_type_check
    def run_hooks_sync(self, is_exit: bool = False):
        """Run extensions synchronously."""
        ctx = (
            contextlib.suppress(StopIteration, StopAsyncIteration)
            if is_exit
            else contextlib.nullcontext()
        )
        for hook in self.hooks:
            with ctx:
                if hook.is_async:
                    raise RuntimeError(
                        f"Extension hook {hook.extension}.{self.HOOK_NAME} "
                        "failed to complete synchronously."
                    )
                else:
                    hook.initialized_hook.__next__()

    @no_type_check
    async def run_hooks_async(self, is_exit: bool = False):
        """Run extensions asynchronously with support for sync lifecycle hooks.

        The ``is_exit`` flag is required as a `StopIteration` cannot be raised from
        within a coroutine.
        """
        ctx = (
            contextlib.suppress(StopIteration, StopAsyncIteration)
            if is_exit
            else contextlib.nullcontext()
        )

        for hook in self.hooks:
            with ctx:
                if hook.is_async:
                    await hook.initialized_hook.__anext__()
                else:
                    hook.initialized_hook.__next__()

    def __enter__(self):
        self.run_hooks_sync()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.run_hooks_sync(is_exit=True)

    async def __aenter__(self):
        await self.run_hooks_async()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.run_hooks_async(is_exit=True)


class OperationContextManager(ExtensionContextManagerBase):
    HOOK_NAME = Extension.on_operation.__name__
    LEGACY_ENTER = "on_request_start"
    LEGACY_EXIT = "on_request_end"


class ValidationContextManager(ExtensionContextManagerBase):
    HOOK_NAME = Extension.on_validate.__name__
    LEGACY_ENTER = "on_validation_start"
    LEGACY_EXIT = "on_validation_end"


class ParsingContextManager(ExtensionContextManagerBase):
    HOOK_NAME = Extension.on_parse.__name__
    LEGACY_ENTER = "on_parsing_start"
    LEGACY_EXIT = "on_parsing_end"


class ExecutingContextManager(ExtensionContextManagerBase):
    HOOK_NAME = Extension.on_execute.__name__
    LEGACY_ENTER = "on_executing_start"
    LEGACY_EXIT = "on_executing_end"
