"""Tests for CypherGlue.render_return_clause and Extends, ReturnElements, Snippet, Verbatim"""

import re
from pprint import pprint
from textwrap import dedent

import pytest

from cypherglue import CypherGlue, Extends, Verbatim


# FIXME remove domain keywords!


def test_render_return_clause_demo():
    elements = (
        # Literals
        "*",  # *,
        ("foo", "bar"),  # bar AS foo,
        # Objects
        (
            "report",
            {  # {
                "lazy": False,  # false,
                "pi": 3.14,  # 3.14,
                "gata": "'Kitty'",  # 'Kitty'
                "hungry": True,  # true
                "chases": ["'ball'", "mouse", False],  # ['ball', mouse, false],
                "mouse": None,  # mouse null
            },
        ),  # } AS report,
        ("time", (("zone", "'UTC'"),)),
        # Extending the `study_value` node/object, embedding an other object
        (
            "study",
            Extends(
                "study_value",
                {  # study_value {
                    ".*": Verbatim,  # .*,
                    "uid": "study_root.uid",  # uid: study_root.uid,
                    "version": Extends(
                        "study_version",
                        (  # version: study_version {
                            ".status",  # .status,
                            # BUG: without None and the sequence-notation, would render as "legs: fingers.count {" instead
                            (
                                "legs",
                                (  # legs: {
                                    ("fingers.count"),  # fingers.count,
                                    ("count", 4),  # count: 4
                                ),
                            ),  # }
                            ".version",  # .version
                        ),
                    ),
                },
            ),
        ),
        # dict also rendered, though perhaps not too useful
        {
            "property": "value.uid",
            "syntax": False,
        },  # {property: value.uid, syntax: false},
        # members of a set rendered as literals, order in a set is not guaranteed
        {'useful: COALESCE(order, "Fuzzy!")'},  # {useful: COALESCE(order, "Fuzzy!")},
        # Amendments to already defined objects (can appear earlier than the object itself)
        (
            "study.version.amendment",
            {  # adds a new property to study.version with mapping as value
                "amended": True,
                "key": "study_version.version",
            },
        ),
        (
            "report.sub",
            Extends(
                "node",
                (  # sub: node {
                    ".*",  # .*
                    ("uid", "report_root.uid"),  # uid: report.uid,
                ),
            ),
        ),
        "report.sub..status",  # .status }
        # No comma after the last element of the block
        ("last_line", "No.Comma"),  # No.Comma AS last_line
    )

    expected = dedent(
        """
        RETURN DISTINCT
            *,
            bar AS foo,
            {
                lazy: false,
                pi: 3.14,
                gata: 'Kitty',
                hungry: true,
                chases: ['ball', mouse, false],
                mouse: null,
                sub: node {
                    .*,
                    uid: report_root.uid,
                    .status
                }
            } AS report,
            {
                zone: 'UTC'
            } AS time,
            study_value {
                .*,
                uid: study_root.uid,
                version: study_version {
                    .status,
                    legs: {
                        count: fingers.count,
                        count: 4
                    },
                    .version,
                    amendment: {
                        amended: true,
                        key: study_version.version
                    }
                }
            } AS study,
            {property: value.uid, syntax: false},
            {useful: COALESCE(order, "Fuzzy!")},
            No.Comma AS last_line
        """
    ).strip()

    print("\n= Input =")
    pprint(input)
    print("= Result =")
    result = CypherGlue.render_return_clause(elements)
    print(result)
    if result != expected:
        print("= Expected =")
        print(expected)
    assert result == expected


def test_render_return_clause_notations():
    example = [
        "x",
        ("y", 100),
        ("z.nested.a", False),
        ("z", (("nested", {"b": ["B1", "B2"], "c": None, "d": True}), "plain")),
        ("z.c", "hi"),
        ("w", 3.19),
    ]

    expected = dedent(
        """
        RETURN DISTINCT
            x,
            100 AS y,
            {
                nested: {
                    b: [B1, B2],
                    c: null,
                    d: true,
                    a: false
                },
                plain: plain,
                c: hi
            } AS z,
            3.19 AS w
    """
    ).strip()

    result = CypherGlue.render_return_clause(example)
    print()
    print(result)
    assert result == expected


def test_render_return_clause_basics():
    elements = (
        "*",
        ("activity_uid", "activity_root.uid"),
        ("activity", Extends("activity_value", {".*": Verbatim})),
        ("activity.status", "vers.status"),
        (
            "change",
            (
                (
                    "username",
                    "coalesce(head([(user:User)-[*0]-() WHERE user.user_id=study_action.author_id | user.username]), study_action.author_id)",
                ),
                ("date", None),
            ),
        ),
        ("visible", "coalesce(activity_root.visibility, fase)"),
    )

    expected = dedent(
        """
        RETURN DISTINCT
            *,
            activity_root.uid AS activity_uid,
            activity_value {
                .*,
                status: vers.status
            } AS activity,
            {
                username: coalesce(head([(user:User)-[*0]-() WHERE user.user_id=study_action.author_id | user.username]), study_action.author_id),
                date: null
            } AS change,
            coalesce(activity_root.visibility, fase) AS visible
    """
    ).strip()

    result = CypherGlue.render_return_clause(elements)
    print()
    print(result)
    assert result == expected


def test_render_return_clause_no_projections():
    elements = (
        ("user_id", "user.uid"),
        ("name", "user.name"),
        ("email", "user.email"),
    )

    expected = dedent(
        """
        RETURN DISTINCT
            user.uid AS user_id,
            user.name AS name,
            user.email AS email
    """
    ).strip()

    result = CypherGlue.render_return_clause(elements)
    print()
    print(result)
    assert result == expected


def test_render_return_clause_multiple_projections():
    elements = (
        (
            "thing",
            Extends(
                "thing_node",
                {
                    None: Verbatim(".*"),
                    "id": "thing_node.id",
                    "name": "thing_node.name",
                },
            ),
        ),
        ("meta", Extends("meta_node", (".*",))),
        ("meta.created", "meta_node.created_at"),
    )

    expected = dedent(
        """
        RETURN DISTINCT
            thing_node {
                .*,
                id: thing_node.id,
                name: thing_node.name
            } AS thing,
            meta_node {
                .*,
                created: meta_node.created_at
            } AS meta
    """
    ).strip()

    result = CypherGlue.render_return_clause(elements)
    print()
    print(result)
    assert result == expected


@pytest.mark.parametrize(
    "elements, expected",
    [
        (["hello"], "RETURN DISTINCT hello"),
        (["hello", "World"], "RETURN DISTINCT hello, World"),
        (("hello",), "RETURN DISTINCT hello"),
        ((Verbatim("hi_there"),), "RETURN DISTINCT hi_there"),
        (("hello", "World"), "RETURN DISTINCT hello, World"),
        ({"hello": Verbatim}, "RETURN DISTINCT hello"),
        ({"hello": Verbatim("World")}, "RETURN DISTINCT World"),
        ({None: Verbatim("World")}, "RETURN DISTINCT World"),
        ({"hello": "world"}, "RETURN DISTINCT world AS hello"),
        (
            {
                "hello": Extends(
                    "World", {".*": Verbatim, ".uid": Verbatim, "foo": "bar"}
                )
            },
            "RETURN DISTINCT World { .*, .uid, foo: bar } AS hello",
        ),
    ],
)
def test_render_return_clause(elements: any, expected: str):
    result = CypherGlue.render_return_clause(elements)
    result = re.sub("\s+", " ", result).strip()
    assert result == expected


def test_render_return_clause_list_of_strings():
    elements = ["hello", "World"]
    expected = dedent(
        """
        RETURN DISTINCT
            hello,
            World
        """
    ).strip()
    result = CypherGlue.render_return_clause(elements)
    assert result == expected


def test_render_return_clause_lists_one_tuple():
    elements = ("hello",)
    expected = dedent(
        """
        RETURN DISTINCT
            hello
        """
    ).strip()
    result = CypherGlue.render_return_clause(elements)
    assert result == expected


def test_render_return_clause_tuple_of_strings():
    elements = ("hello", "World")
    expected = dedent(
        """
        RETURN DISTINCT
            hello,
            World
        """
    ).strip()
    result = CypherGlue.render_return_clause(elements)
    assert result == expected


@pytest.mark.parametrize(
    "items, expected",
    [
        (["*"], "RETURN DISTINCT\n    *"),  # star
        (["movies"], "RETURN DISTINCT\n    movies"),  # single str item
        (  # list of two-tuples
            [("title", "movie.title")],
            "RETURN DISTINCT\n    movie.title AS title",
        ),
        (  # sequence of mixed including dict struct
            (("movie", {"title": "'Alice'", "year": 1923}), "director"),
            "RETURN DISTINCT\n    {\n        title: 'Alice',\n        year: 1923\n    } AS movie,\n    director",
        ),
        (  # Extends, Verbatim class
            {
                "movie": {"title": "'Alice'", "year": 1923},
                "director": Extends("person", {".*": Verbatim, "role": "'director'"}),
            },
            dedent(
                """
        RETURN DISTINCT
            {
                title: 'Alice',
                year: 1923
            } AS movie,
            person {
                .*,
                role: 'director'
            } AS director"""
            ).strip(),
        ),
        (  # amendment, with Verbatim instantiated
            {
                "movie": {"title": "'Alice'", "year": 1923},
                "director": Extends("person", [Verbatim(".*")]),
                "director.role": "'director'",
            },
            dedent(
                """
        RETURN DISTINCT
            {
                title: 'Alice',
                year: 1923
            } AS movie,
            person {
                .*,
                role: 'director'
            } AS director"""
            ).strip(),
        ),
    ],
)
def test_render_return_clause(items, expected):
    output = CypherGlue.render_return_clause(items)
    assert output == expected
