import dataclasses
import typing
from textwrap import dedent

import pytest

import strawberry
from strawberry.types.unset import UNSET


def test_mutation():
    @strawberry.type
    class Query:
        hello: str = "Hello"

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def say(self) -> str:
            return "Hello!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    query = "mutation { say }"

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["say"] == "Hello!"


def test_mutation_with_input_type():
    @strawberry.input
    class SayInput:
        name: str
        age: int

    @strawberry.type
    class Query:
        hello: str = "Hello"

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def say(self, input: SayInput) -> str:
            return f"Hello {input.name} of {input.age} years old!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    query = 'mutation { say(input: { name: "Patrick", age: 10 }) }'

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["say"] == "Hello Patrick of 10 years old!"


def test_mutation_reusing_input_types():
    @strawberry.input
    class SayInput:
        name: str
        age: int

    @strawberry.type
    class Query:
        hello: str = "Hello"

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def say(self, input: SayInput) -> str:
            return f"Hello {input.name} of {input.age} years old!"

        @strawberry.mutation
        def say2(self, input: SayInput) -> str:
            return f"Hello {input.name} of {input.age}!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    query = 'mutation { say2(input: { name: "Patrick", age: 10 }) }'

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["say2"] == "Hello Patrick of 10!"


def test_unset_types():
    @strawberry.type
    class Query:
        hello: str = "Hello"

    @strawberry.input
    class InputExample:
        name: str
        age: typing.Optional[int] = UNSET

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def say(self, name: typing.Optional[str] = UNSET) -> str:  # type: ignore
            if name is UNSET:
                return "Name is unset"

            return f"Hello {name}!"

        @strawberry.mutation
        def say_age(self, input: InputExample) -> str:
            age = "unset" if input.age is UNSET else input.age

            return f"Hello {input.name} of age {age}!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    query = 'mutation { say sayAge(input: { name: "P"}) }'

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["say"] == "Name is unset"
    assert result.data["sayAge"] == "Hello P of age unset!"


def test_unset_types_name_with_underscore():
    @strawberry.type
    class Query:
        hello: str = "Hello"

    @strawberry.input
    class InputExample:
        first_name: str
        age: typing.Optional[str] = UNSET

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def say(self, first_name: typing.Optional[str] = UNSET) -> str:  # type: ignore
            if first_name is UNSET:
                return "Name is unset"

            if first_name == "":
                return "Hello Empty!"

            return f"Hello {first_name}!"

        @strawberry.mutation
        def say_age(self, input: InputExample) -> str:
            age = "unset" if input.age is UNSET else input.age
            age = "empty" if age == "" else age

            return f"Hello {input.first_name} of age {age}!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    query = """mutation {
        one: say
        two: say(firstName: "Patrick")
        three: say(firstName: "")
        empty: sayAge(input: { firstName: "Patrick", age: "" })
        null: sayAge(input: { firstName: "Patrick", age: null })
        sayAge(input: { firstName: "Patrick" })
    }"""

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["one"] == "Name is unset"
    assert result.data["two"] == "Hello Patrick!"
    assert result.data["three"] == "Hello Empty!"
    assert result.data["empty"] == "Hello Patrick of age empty!"
    assert result.data["null"] == "Hello Patrick of age None!"
    assert result.data["sayAge"] == "Hello Patrick of age unset!"


def test_unset_types_stringify_empty():
    @strawberry.type
    class Query:
        hello: str = "Hello"

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def say(self, first_name: typing.Optional[str] = UNSET) -> str:  # type: ignore
            return f"Hello {first_name}!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    query = """mutation {
        say
    }"""

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["say"] == "Hello !"

    query = """mutation {
        say(firstName: null)
    }"""

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["say"] == "Hello None!"


def test_converting_to_dict_with_unset():
    @strawberry.type
    class Query:
        hello: str = "Hello"

    @strawberry.input
    class Input:
        name: typing.Optional[str] = UNSET

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def say(self, input: Input) -> str:
            data = dataclasses.asdict(input)

            if data["name"] is UNSET:
                return "Hello 🤨"

            return f"Hello {data['name']}!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    query = """mutation {
        say(input: {})
    }"""

    result = schema.execute_sync(query)

    assert not result.errors
    assert result.data["say"] == "Hello 🤨"


def test_mutation_deprecation_reason():
    @strawberry.type
    class Query:
        hello: str = "world"

    @strawberry.type
    class Mutation:
        @strawberry.mutation(deprecation_reason="Your reason")
        def say(self, name: str) -> str:
            return f"Hello {name}!"

    schema = strawberry.Schema(query=Query, mutation=Mutation)

    assert str(schema) == dedent(
        """\
        type Mutation {
          say(name: String!): String! @deprecated(reason: "Your reason")
        }

        type Query {
          hello: String!
        }"""
    )


@pytest.fixture
def maybe_schema() -> strawberry.Schema:
    @strawberry.type
    class User:
        name: str
        phone: typing.Optional[str]

    user = User(name="Patrick", phone=None)

    @strawberry.type
    class Query:
        @strawberry.field
        def user(self) -> User:
            return user

    @strawberry.input
    class UpdateUserInput:
        phone: strawberry.Maybe[str]

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        def update_user(self, input: UpdateUserInput) -> User:
            if strawberry.not_unset(input.phone):
                user.phone = input.phone
            return user

    return strawberry.Schema(query=Query, mutation=Mutation)


user_query = """
{
    user {
        phone
    }
}
"""


def set_phone(schema: strawberry.Schema, phone: typing.Optional[str]) -> dict:
    query = """
    mutation ($phone: String) {
        updateUser(input: { phone: $phone }) {
            phone
        }
    }
    """

    result = schema.execute_sync(query, variable_values={"phone": phone})
    assert not result.errors
    assert result.data
    return result.data["updateUser"]


def get_user(schema: strawberry.Schema) -> dict:
    result = schema.execute_sync(user_query)
    assert not result.errors
    assert result.data
    return result.data["user"]


def test_maybe_none_to_some(maybe_schema: strawberry.Schema) -> None:
    assert get_user(maybe_schema)["phone"] is None
    res = set_phone(maybe_schema, "123")
    assert res["phone"] == "123"


def test_maybe_some_to_none(maybe_schema: strawberry.Schema) -> None:
    assert get_user(maybe_schema)["phone"] is None
    set_phone(maybe_schema, "123")
    res = set_phone(maybe_schema, None)
    assert res["phone"] is None


def test_maybe_absent_value(maybe_schema: strawberry.Schema) -> None:
    set_phone(maybe_schema, "123")

    query = """
    mutation {
        updateUser(input: {}) {
            phone
        }
    }
    """
    result = maybe_schema.execute_sync(query)
    assert not result.errors
    assert result.data
    assert result.data["updateUser"]["phone"] == "123"
    # now check the reverse case.

    set_phone(maybe_schema, None)
    result = maybe_schema.execute_sync(query)
    assert not result.errors
    assert result.data
    assert result.data["updateUser"]["phone"] is None
