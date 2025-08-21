"""Tests for Snippet registration into CypherGlue"""

import pytest

from cypherglue import CypherGlue, Snippet


def test_register_snippet_instance():
    glue = CypherGlue()
    snippet = Snippet("node")
    glue.register(snippet)
    assert glue.snippets["node"] is snippet


def test_register_snippets_twice():
    glue = CypherGlue()
    glue.register(Snippet("inst1"))
    glue.register(Snippet("inst2"))


def test_register_snippets_duplicate_name_raises():
    glue = CypherGlue()
    glue.register(Snippet("dup"))
    with pytest.raises(ValueError, match="already registered"):
        glue.register(Snippet("dup"))


def test_register_invalid_type_raises():
    glue = CypherGlue()
    with pytest.raises(TypeError):
        glue.register(123)


def test_register_snippet_subclass():
    glue = CypherGlue()

    class MySnippet(Snippet):
        name = "x"

    glue.register(MySnippet)
    assert "x" in glue.snippets

    glue.register(MySnippet("y"))
    assert "y" in glue.snippets


def test_register_decorator_form():
    glue = CypherGlue()

    @glue.register("decorated")
    class S(Snippet):
        pass

    assert "decorated" in glue.snippets


def test_register_instance():
    registration_name = "movie"

    snippet = Snippet(
        name=registration_name, query="MATCH (m:Movies)", returns=("m",), defines={"m"}
    )
    glue = CypherGlue()
    glue.register(snippet)

    assert registration_name in glue.snippets
    assert glue.snippets[registration_name] is snippet
    assert isinstance(snippet, Snippet)
    assert set(snippet.defines).issubset(set(glue._vars_to_snippet.keys()))


def test_register_subclass():
    registration_name = "movie"

    class MySnippet(Snippet):
        name = registration_name
        query = "MATCH (m:Movies)"
        returns = ("m",)
        defines = ["m"]

    glue = CypherGlue()
    glue.register(MySnippet)

    assert registration_name in glue.snippets
    snippet = glue.snippets[registration_name]
    assert isinstance(snippet, Snippet)
    assert snippet.name == registration_name
    assert snippet.query == MySnippet.query
    assert snippet.returns == MySnippet.returns
    assert snippet.defines == frozenset(MySnippet.defines)
    assert set(snippet.defines).issubset(set(glue._vars_to_snippet.keys()))


def test_decorator_registration():
    registration_name = "decorated_snippet"

    glue = CypherGlue()

    @glue.register
    class DecoratedSnippet(Snippet):
        name = registration_name
        query = "MATCH (d:Decorated)"
        returns = ("*",)
        defines = ["d"]

    assert registration_name in glue.snippets
    snippet = glue.snippets[registration_name]
    assert isinstance(snippet, DecoratedSnippet)
    assert set(snippet.defines).issubset(set(glue._vars_to_snippet.keys()))


def test_decorator_registration_with_name():
    registration_name = "art_deco_snippet"

    glue = CypherGlue()

    @glue.register(registration_name)
    class DecoratedSnippet(Snippet):
        name = "decorated_snippet"
        query = "MATCH (d:Decorated)"
        returns = ("*",)
        defines = ("d",)

    assert registration_name in glue.snippets
    snippet = glue.snippets[registration_name]
    assert isinstance(snippet, DecoratedSnippet)
    assert set(snippet.defines).issubset(set(glue._vars_to_snippet.keys()))
