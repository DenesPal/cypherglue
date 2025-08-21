"""Tests for Snippet class"""

from types import MappingProxyType

import pytest

from cypherglue import Extends, Snippet, Verbatim


def test_snippet_requires_name():
    with pytest.raises(TypeError, match="Name must be specified."):
        Snippet()


@pytest.mark.parametrize(
    "returns_input, expected",
    [
        ("uid", ("uid",)),
        (["name", "uid"], ("name", "uid")),
        ({"id": "node.id"}, MappingProxyType({"id": "node.id"})),
    ],
)
def test_returns_normalization(returns_input, expected):
    s = Snippet(name="Test", returns=returns_input)
    assert s.returns == expected


@pytest.mark.parametrize(
    "query, labels, expected",
    [
        (
            """
        MATCH (n:{feature})
        RETURN n
        """,
            {"feature": "Movie"},
            "MATCH (n:Movie)\nRETURN n",
        ),
        (
            "\n    CREATE (p:{Person})",
            {"feature": "Movie", "Person": "Actor"},
            "CREATE (p:Actor)",
        ),
    ],
)
def test_query_label_substitution(query, labels, expected):
    snip = Snippet(name="X", query=query, labels=labels)
    query, params, returns = snip.render({})
    assert query == expected


def test_snippet_clone_overrides_fields():
    original = Snippet(
        name="original",
        query="MATCH (a)",
        defines=["a"],
        always=True,
    )
    clone = original.clone(name="cloned", defines=["b"])

    assert clone.name == "cloned"
    assert clone.query == "MATCH (a)"
    assert clone.defines == frozenset(["b"])
    assert clone.always is True
    assert original.defines == frozenset(["a"])  # original unchanged


def test_snippet_render_without_labels():
    s = Snippet(name="Simple", query="MATCH (x)", returns=["x"])
    q, params, ret = s.render()
    assert q == "MATCH (x)"
    assert params == {}
    assert ret == ("x",)


def test_snippet_render_with_labels():
    s = Snippet(
        name="Labeled",
        query="MATCH (n:{LABEL})",
        labels={"LABEL": "Thing"},
    )
    query, _, _ = s.render()
    assert query == "MATCH (n:Thing)"


def test_verbatim_string_rendering():
    v = Verbatim("foo.bar")
    assert str(v) == "foo.bar"
    assert v.expression == "foo.bar"


def test_extends_structure():
    elements = [("name", Verbatim("n.name")), ("age", Verbatim("n.age"))]
    ext = Extends(name="person", elements=elements)
    assert ext.name == "person"
    assert ext.elements == elements


@pytest.mark.parametrize(
    "field, value",
    [
        ("defines", ["x", "y"]),
        ("requires", ["a"]),
        ("parameters", ["p1", "p2"]),
    ],
)
def test_snippet_frozensets(field, value):
    s = Snippet(name="FrozenTest", query="MATCH (n)", **{field: value})
    assert getattr(s, field) == frozenset(value)


def test_subclassing_snippet():
    class MySnippet(Snippet):
        name = "movie"
        query = "MATCH (m:Movies)"
        returns = ("m",)
        defines = ["m"]

    msn = MySnippet()
    assert msn.name == "movie"
    assert msn.query == "MATCH (m:Movies)"
    assert isinstance(msn.returns, tuple)
    assert msn.returns == ("m",)
    assert isinstance(msn.defines, frozenset)
    assert msn.defines == frozenset(["m"])
