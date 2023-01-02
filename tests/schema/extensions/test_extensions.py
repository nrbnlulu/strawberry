import dataclasses
import json
from typing import Optional, Type
from unittest.mock import patch

import pytest
from graphql import ExecutionResult as GraphQLExecutionResult
from graphql import GraphQLError
from graphql import execute as original_execute

import strawberry
from strawberry.exceptions import StrawberryGraphQLError
from strawberry.extensions import Extension


def test_base_extension():
    @strawberry.type
    class Person:
        name: str = "Jess"

    @strawberry.type
    class Query:
        @strawberry.field
        def person(self) -> Person:
            return Person()

    schema = strawberry.Schema(query=Query, extensions=[Extension])

    query = """
        query {
            person {
                name
            }
        }
    """

    result = schema.execute_sync(query)

    assert not result.errors

    assert result.extensions == {}


def test_extension_access_to_parsed_document():
    query_name = ""

    class MyExtension(Extension):
        def on_parse(self):
            nonlocal query_name
            yield
            query_definition = self.execution_context.graphql_document.definitions[0]
            query_name = query_definition.name.value

    @strawberry.type
    class Person:
        name: str = "Jess"

    @strawberry.type
    class Query:
        @strawberry.field
        def person(self) -> Person:
            return Person()

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])

    query = """
        query TestQuery {
            person {
                name
            }
        }
    """

    result = schema.execute_sync(query)

    assert not result.errors
    assert query_name == "TestQuery"


def test_extension_access_to_errors():
    execution_errors = []

    class MyExtension(Extension):
        def on_request(self):
            nonlocal execution_errors
            yield
            execution_errors = self.execution_context.errors

    @strawberry.type
    class Person:
        name: str = "Jess"

    @strawberry.type
    class Query:
        @strawberry.field
        def person(self) -> Person:
            return None  # type: ignore

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])

    query = """
        query TestQuery {
            person {
                name
            }
        }
    """

    result = schema.execute_sync(query)

    assert len(result.errors) == 1
    assert execution_errors == result.errors


def test_extension_access_to_root_value():
    root_value = None

    class MyExtension(Extension):
        def on_request(self):
            nonlocal root_value
            yield
            root_value = self.execution_context.root_value

    @strawberry.type
    class Query:
        @strawberry.field
        def hi(self) -> str:
            return "👋"

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])

    query = "{ hi }"

    result = schema.execute_sync(query, root_value="ROOT")

    assert not result.errors
    assert root_value == "ROOT"


@dataclasses.dataclass
class DefaultSchemaQuery:
    query_type: type
    query: str


class TestAbleExtension(Extension):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.called_hooks = set()

    expected = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
    called_hooks: set

    @classmethod
    def preform_test(cls):
        assert cls.called_hooks == cls.expected


@pytest.fixture()
def default_query_types_and_query() -> DefaultSchemaQuery:
    @strawberry.type
    class Person:
        name: str = "Jess"

    @strawberry.type
    class Query:
        @strawberry.field
        def person(self) -> Person:
            return Person()

    query = "query TestQuery { person { name } }"
    return DefaultSchemaQuery(query_type=Query, query=query)


@pytest.fixture()
def async_extension() -> Type[TestAbleExtension]:
    class MyExtension(TestAbleExtension):
        async def on_request(self):
            self.called_hooks.add(1)
            yield
            self.called_hooks.add(2)

        async def on_validate(self):
            self.called_hooks.add(3)
            yield
            self.called_hooks.add(4)

        async def on_parse(self):
            self.called_hooks.add(5)
            yield
            self.called_hooks.add(6)

        async def on_execute(self):
            self.called_hooks.add(7)
            yield
            self.called_hooks.add(8)

        async def get_results(self):
            self.called_hooks.add(9)
            return {"example": "example"}

        async def resolve(self, _next, root, info, *args, **kwargs):
            self.called_hooks.add(10)
            return _next(root, info, *args, **kwargs)

    return MyExtension


@pytest.fixture()
def sync_extension() -> Type[TestAbleExtension]:
    class MyExtension(TestAbleExtension):
        def on_request(self):
            self.called_hooks.add(1)
            yield
            self.called_hooks.add(2)

        def on_validate(self):
            self.called_hooks.add(3)
            yield
            self.called_hooks.add(4)

        def on_parse(self):
            self.called_hooks.add(5)
            yield
            self.called_hooks.add(6)

        def on_execute(self):
            self.called_hooks.add(7)
            yield
            self.called_hooks.add(8)

        def get_results(self):
            self.called_hooks.add(9)
            return {"example": "example"}

        def resolve(self, _next, root, info, *args, **kwargs):
            self.called_hooks.add(10)
            return _next(root, info, *args, **kwargs)

    return MyExtension


@pytest.mark.asyncio
async def test_async_extension_hooks(default_query_types_and_query, async_extension):
    schema = strawberry.Schema(
        query=default_query_types_and_query.query_type, extensions=[async_extension]
    )

    result = await schema.execute(default_query_types_and_query.query)
    assert result.errors is None

    async_extension.preform_test()


@pytest.mark.asyncio
async def test_mixed_sync_and_async_extension_hooks(
    default_query_types_and_query, sync_extension
):
    class MyExtension(sync_extension):
        async def on_request(self):
            self.called_hooks.add(1)
            yield
            self.called_hooks.add(2)

        async def on_parse(self):
            self.called_hooks.add(5)
            yield
            self.called_hooks.add(6)

    @strawberry.type
    class Person:
        name: str = "Jess"

    @strawberry.type
    class Query:
        @strawberry.field
        def person(self) -> Person:
            return Person()

    schema = strawberry.Schema(
        query=default_query_types_and_query.query_type, extensions=[MyExtension]
    )
    result = await schema.execute(default_query_types_and_query.query)
    assert result.errors is None
    MyExtension.preform_test()


async def test_sync_extension_hooks(default_query_types_and_query, sync_extension):
    schema = strawberry.Schema(
        query=default_query_types_and_query.query_type,
        extensions=[
            sync_extension,
        ],
    )

    result = schema.execute_sync(default_query_types_and_query.query)
    assert result.errors is None

    sync_extension.preform_test()


async def test_extension_no_yield(default_query_types_and_query):
    class SyncExt(TestAbleExtension):
        expected = {1, 2}

        def on_request(self):
            self.called_hooks.add(1)

        async def on_parse(self):
            self.called_hooks.add(2)

    schema = strawberry.Schema(
        query=default_query_types_and_query.query_type, extensions=[SyncExt]
    )

    result = await schema.execute(default_query_types_and_query.query)
    assert result.errors is None

    SyncExt.preform_test()


def test_warning_about_async_get_results_hooks_in_sync_context():
    class MyExtension(Extension):
        async def get_results(self):
            pass

    @strawberry.type
    class Query:
        @strawberry.field
        def string(self) -> str:
            return ""

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])
    query = "query { string }"

    with pytest.raises(RuntimeError) as exc_info:
        schema.execute_sync(query)
        msg = "Cannot use async extension hook during sync execution"
        assert str(exc_info.value) == msg


@pytest.mark.asyncio
async def test_dont_swallow_errors_in_parsing_hooks():
    class MyExtension(Extension):
        def on_parse(self):
            raise Exception("This shouldn't be swallowed")

    @strawberry.type
    class Query:
        @strawberry.field
        def ping(self) -> str:
            return "pong"

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])
    query = "query { string }"

    with pytest.raises(Exception, match="This shouldn't be swallowed"):
        schema.execute_sync(query)

    with pytest.raises(Exception, match="This shouldn't be swallowed"):
        await schema.execute(query)


def test_on_parsing_end_called_when_errors():
    execution_errors = False

    class MyExtension(Extension):
        def on_parse(self):
            nonlocal execution_errors
            yield
            execution_context = self.execution_context
            execution_errors = execution_context.errors

    @strawberry.type
    class Query:
        @strawberry.field
        def ping(self) -> str:
            return "pong"

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])
    query = "query { string"  # Invalid query

    result = schema.execute_sync(query)
    assert result.errors

    assert result.errors == execution_errors


def test_extension_override_execution():
    class MyExtension(Extension):
        def on_execute(self):
            # Always return a static response
            self.execution_context.result = GraphQLExecutionResult(
                data={
                    "surprise": "data",
                },
                errors=[],
            )

    @strawberry.type
    class Query:
        @strawberry.field
        def ping(self) -> str:
            return "pong"

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])

    query = """
        query TestQuery {
            ping
        }
    """

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data == {
        "surprise": "data",
    }


@pytest.mark.asyncio
async def test_extension_override_execution_async():
    class MyExtension(Extension):
        def on_execute(self):
            # Always return a static response
            self.execution_context.result = GraphQLExecutionResult(
                data={
                    "surprise": "data",
                },
                errors=[],
            )

    @strawberry.type
    class Query:
        @strawberry.field
        def ping(self) -> str:
            return "pong"

    schema = strawberry.Schema(query=Query, extensions=[MyExtension])

    query = """
        query TestQuery {
            ping
        }
    """

    result = await schema.execute(query)

    assert not result.errors
    assert result.data == {
        "surprise": "data",
    }


@patch("strawberry.schema.execute.original_execute", wraps=original_execute)
def test_execution_cache_example(mock_original_execute):
    # Test that the example of how to use the on_executing_start hook in the
    # docs actually works

    response_cache = {}

    class ExecutionCache(Extension):
        def on_execute(self):
            # Check if we've come across this query before
            execution_context = self.execution_context
            self.cache_key = (
                f"{execution_context.query}:{json.dumps(execution_context.variables)}"
            )
            if self.cache_key in response_cache:
                self.execution_context.result = response_cache[self.cache_key]
            yield
            if self.cache_key not in response_cache:
                response_cache[self.cache_key] = execution_context.result

    @strawberry.type
    class Query:
        @strawberry.field
        def ping(self, return_value: Optional[str] = None) -> str:
            if return_value is not None:
                return return_value
            return "pong"

    schema = strawberry.Schema(
        Query,
        extensions=[
            ExecutionCache,
        ],
    )

    query = """
        query TestQuery($returnValue: String) {
            ping(returnValue: $returnValue)
        }
    """
    result = schema.execute_sync(query)
    assert not result.errors
    assert result.data == {
        "ping": "pong",
    }

    assert mock_original_execute.call_count == 1

    # This should be cached
    result = schema.execute_sync(query)
    assert not result.errors
    assert result.data == {
        "ping": "pong",
    }

    assert mock_original_execute.call_count == 1

    # Calling with different variables should not be cached
    result = schema.execute_sync(
        query,
        variable_values={
            "returnValue": "plong",
        },
    )
    assert not result.errors
    assert result.data == {
        "ping": "plong",
    }

    assert mock_original_execute.call_count == 2


@patch("strawberry.schema.execute.original_execute", wraps=original_execute)
def test_execution_reject_example(mock_original_execute):
    # Test that the example of how to use the on_executing_start hook in the
    # docs actually works

    class RejectSomeQueries(Extension):
        def on_execute(self):
            # Reject all operations called "RejectMe"
            execution_context = self.execution_context
            if execution_context.operation_name == "RejectMe":
                self.execution_context.result = GraphQLExecutionResult(
                    data=None,
                    errors=[GraphQLError("Well you asked for it")],
                )

    @strawberry.type
    class Query:
        @strawberry.field
        def ping(self) -> str:
            return "pong"

    schema = strawberry.Schema(
        Query,
        extensions=[
            RejectSomeQueries,
        ],
    )

    query = """
        query TestQuery {
            ping
        }
    """
    result = schema.execute_sync(query, operation_name="TestQuery")
    assert not result.errors
    assert result.data == {
        "ping": "pong",
    }

    assert mock_original_execute.call_count == 1

    query = """
        query RejectMe {
            ping
        }
    """
    result = schema.execute_sync(query, operation_name="RejectMe")
    assert result.errors == [GraphQLError("Well you asked for it")]

    assert mock_original_execute.call_count == 1


def test_extend_error_format_example():
    # Test that the example of how to extend error format

    class ExtendErrorFormat(Extension):
        def on_request(self):
            yield
            result = self.execution_context.result
            if getattr(result, "errors", None):
                result.errors = [
                    StrawberryGraphQLError(
                        extensions={"additional_key": "additional_value"},
                        nodes=error.nodes,
                        source=error.source,
                        positions=error.positions,
                        path=error.path,
                        original_error=error.original_error,
                        message=error.message,
                    )
                    for error in result.errors
                ]

    @strawberry.type
    class Query:
        @strawberry.field
        def ping(self) -> str:
            raise Exception("This error occurred while querying the ping field")

    schema = strawberry.Schema(query=Query, extensions=[ExtendErrorFormat])
    query = """
        query TestQuery {
            ping
        }
    """

    result = schema.execute_sync(query)
    assert result.errors[0].extensions == {"additional_key": "additional_value"}
    assert (
        result.errors[0].message == "This error occurred while querying the ping field"
    )
    assert result.data is None
