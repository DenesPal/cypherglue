"""Tests for CypherGlue.render"""

from textwrap import dedent

import pytest

from cypherglue import CypherGlue, Extends, Snippet


@pytest.fixture(scope="session")
def movies_query() -> CypherGlue:
    """Fixture returns a query for the Movie tutorial database"""

    glue = CypherGlue()

    @glue.register("movie")
    class Movies(Snippet):
        """Movies
        properties: released, tagline, title
        relationships-in: ACTED_IN, DIRECTED, PRODUCED, REVIEWED, WROTE
        """

        query = "MATCH (movie:Movie)"
        defines = ("movie",)  # defines movie query variable
        returns = {"movie": Extends("movie", (".*",))}  # returns movie structure
        always = True

    @glue.register("director")
    class Director(Snippet):
        query = "MATCH (movie)<-[:DIRECTED]-(director:Person)"
        requires = {"movie"}  # requires movie query variable
        defines = {"director"}  # defines director query variable
        returns = {
            "movie.director": "director"
        }  # extends returned movie structure with director property

    @glue.register("producer")
    class Producer(Snippet):
        query = "MATCH (movie)<-[:PRODUCED]-(producer:Person)"
        requires = {"movie"}
        defines = {"producer"}
        returns = {"movie.producer": Extends("producer", [".*"])}

    @glue.register("producer_follows")
    class ProducerFollows(Snippet):
        query = "MATCH (producer)-[:FOLLOWS]->(followed:Person)"
        requires = {"producer"}
        defines = {"followed"}
        returns = {
            "movie.producer.follows": "COLLECT(followed)"
        }  # extends movie.producer with a list of followed

    @glue.register("actors")
    class Actors(Snippet):
        query = "MATCH (movie)<-[act:ACTED_IN]-(actor:Person)"
        requires = {"movie"}
        defines = {"actor"}
        returns = {"actors": "COLLECT(actor {.*, roles: act.roles})"}

    @glue.register("writer")
    class Writer(Snippet):
        query = "MATCH (movie)<-[:WROTE]-(writer:Person)"
        requires = {"movie"}
        defines = {"writer"}
        returns = {"movie.writer": "writer"}

    return glue


def test_renders_always_snippet(movies_query):
    """CypherGlue always renders Snippets with `always=True` property"""
    query, params = movies_query.render()
    assert (
        query
        == "MATCH (movie:Movie)\nRETURN DISTINCT\n    movie {\n        .*\n    } AS movie"
    )
    assert params == {}


def test_renders_expands_1(movies_query):
    """CypherGlue renders a Snippet selected with `expand`"""
    query, params = movies_query.render(expand={"producer"})
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[:PRODUCED]-(producer:Person)
        RETURN DISTINCT
            movie {
                .*,
                producer: producer {
                    .*
                }
            } AS movie
    """
        ).strip()
    )
    assert params == {}


def test_renders_expands_2(movies_query):
    """CypherGlue renders Snippets selected with `expand`"""
    query, params = movies_query.render(expand={"actors", "writer"})
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[act:ACTED_IN]-(actor:Person)
        MATCH (movie)<-[:WROTE]-(writer:Person)
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie,
            COLLECT(actor {.*, roles: act.roles}) AS actors
    """
        ).strip()
    )
    assert params == {}


def test_renders_by_dependency(movies_query):
    """CypherGlue renders Snippet by dependency of a selected Snippet"""
    query, params = movies_query.render(expand={"producer_follows"})
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[:PRODUCED]-(producer:Person)
        MATCH (producer)-[:FOLLOWS]->(followed:Person)
        WITH movie, producer, COLLECT(followed) AS producer_follows
        RETURN DISTINCT
            movie {
                .*,
                producer: producer {
                    .*,
                    follows: producer_follows
                }
            } AS movie
    """
        ).strip()
    )
    assert params == {}


def test_renders_filter(movies_query):
    """CypherGlue renders filter"""
    query, params = movies_query.render(filter_by={"movie.released": {">": 1980}})
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WHERE movie.released > $_filter_movie__released_0
        RETURN DISTINCT
            movie {
                .*
            } AS movie
    """
        ).strip()
    )
    assert params == {"_filter_movie__released_0": 1980}


def test_renders_filter_early(movies_query):
    """CypherGlue is eager to render filter as soon as the filtered object becomes available"""
    query, params = movies_query.render(
        expand={"writer"}, filter_by={"movie.released": {"$gt": 1980}}
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WHERE movie.released > $_filter_movie__released_0
        MATCH (movie)<-[:WROTE]-(writer:Person)
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {"_filter_movie__released_0": 1980}


def test_renders_filter_early_2(movies_query):
    """CypherGlue is eager to render filters as soon as the filtered objects become available"""
    query, params = movies_query.render(
        expand={"writer"},
        filter_by={
            "writer.name": {"IN": ["Nancy Meyers", "Lilly Wachowski"]},
            "movie.released": {">": 1980},
        },
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WHERE movie.released > $_filter_movie__released_0
        MATCH (movie)<-[:WROTE]-(writer:Person)
        WHERE writer.name IN $_filter_writer__name_0
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {
        "_filter_movie__released_0": 1980,
        "_filter_writer__name_0": ["Nancy Meyers", "Lilly Wachowski"],
    }


def test_renders_ordering_1(movies_query):
    """CypherGlue is eager to render sorting"""
    query, params = movies_query.render(expand={"writer"}, order_by=["movie.released"])
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WITH DISTINCT * ORDER BY movie.released ASC
        MATCH (movie)<-[:WROTE]-(writer:Person)
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {}


def test_renders_ordering_2(movies_query):
    """CypherGlue renders sorting (Snippet selected implicitly when required by a sorting key)"""
    query, params = movies_query.render(order_by=(("writer.name", "DESC"),))
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[:WROTE]-(writer:Person)
        WITH DISTINCT * ORDER BY writer.name DESC
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {}


def test_renders_ordering_3(movies_query):
    """CypherGlue sorts by multiple expressions"""
    query, params = movies_query.render(
        order_by=[("movie.released", "DESC"), "movie.title"]
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WITH DISTINCT * ORDER BY movie.released DESC, movie.title ASC
        RETURN DISTINCT
            movie {
                .*
            } AS movie
    """
        ).strip()
    )
    assert params == {}


def test_renders_ordering_4(movies_query):
    """CypherGlue is renders sorting after filters"""
    query, params = movies_query.render(
        expand={"writer"},
        order_by=["movie.title"],
        filter_by={"writer.name": {"STARTS WITH": "Aaron"}},
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[:WROTE]-(writer:Person)
        WHERE writer.name STARTS WITH $_filter_writer__name_0
        WITH DISTINCT * ORDER BY movie.title ASC
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {"_filter_writer__name_0": "Aaron"}


def test_renders_pagination(movies_query):
    """CypherGlue is eager to render pagination"""
    query, params = movies_query.render(expand={"writer"}, limit=42, skip=10)
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WITH DISTINCT * SKIP $_skip LIMIT $_limit
        MATCH (movie)<-[:WROTE]-(writer:Person)
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {"_skip": 10, "_limit": 42}


def test_renders_pagination_with_ordering(movies_query):
    """CypherGlue is eager to render pagination with the order clause"""
    query, params = movies_query.render(
        expand=["writer"], order_by=["movie.title"], skip=3
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WITH DISTINCT * ORDER BY movie.title ASC SKIP $_skip
        MATCH (movie)<-[:WROTE]-(writer:Person)
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {"_skip": 3}


def test_renders_pagination_with_orderings(movies_query):
    """CypherGlue renders pagination with the order clause"""
    query, params = movies_query.render(
        limit=3, order_by=["writer.name", "movie.title"]
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[:WROTE]-(writer:Person)
        WITH DISTINCT * ORDER BY writer.name ASC, movie.title ASC LIMIT $_limit
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {"_limit": 3}


def test_renders_pagination_after_filters_1(movies_query):
    """CypherGlue is renders pagination after filters"""
    query, params = movies_query.render(
        expand={"writer"},
        filter_by={"writer.name": {"STARTS WITH": "Aaron"}},
        skip=10,
        limit=5,
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[:WROTE]-(writer:Person)
        WHERE writer.name STARTS WITH $_filter_writer__name_0
        WITH DISTINCT * SKIP $_skip LIMIT $_limit
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {"_filter_writer__name_0": "Aaron", "_skip": 10, "_limit": 5}


def test_renders_pagination_after_filters_2(movies_query):
    """CypherGlue is renders pagination after filters"""
    query, params = movies_query.render(
        expand={"writer"},
        order_by=["movie.title"],
        filter_by={
            "writer.name": {"STARTS WITH": "Aaron"},
            "movie.released": {"$lt": 1999},
        },
        skip=10,
        limit=5,
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WHERE movie.released < $_filter_movie__released_0
        MATCH (movie)<-[:WROTE]-(writer:Person)
        WHERE writer.name STARTS WITH $_filter_writer__name_0
        WITH DISTINCT * ORDER BY movie.title ASC SKIP $_skip LIMIT $_limit
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {
        "_skip": 10,
        "_limit": 5,
        "_filter_movie__released_0": 1999,
        "_filter_writer__name_0": "Aaron",
    }


def test_render_with_params_passthrough(movies_query):
    """CypherGlue is renders pagination after filters"""
    query, params = movies_query.render(
        params={"hello": "Mulholland drive"},
        expand={"writer"},
        order_by=["movie.title"],
        filter_by={
            "writer.name": {"STARTS WITH": "Aaron"},
            "movie.released": {"$lt": 1999},
        },
        skip=10,
        limit=5,
    )
    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        WHERE movie.released < $_filter_movie__released_0
        MATCH (movie)<-[:WROTE]-(writer:Person)
        WHERE writer.name STARTS WITH $_filter_writer__name_0
        WITH DISTINCT * ORDER BY movie.title ASC SKIP $_skip LIMIT $_limit
        RETURN DISTINCT
            movie {
                .*,
                writer: writer
            } AS movie
    """
        ).strip()
    )
    assert params == {
        "_skip": 10,
        "_limit": 5,
        "_filter_movie__released_0": 1999,
        "_filter_writer__name_0": "Aaron",
        "hello": "Mulholland drive",
    }


def test_render_missing_required_param_raises():
    glue = CypherGlue()
    glue.register(Snippet(name="param", parameters=["foo"], defines=["bar"]))

    with pytest.raises(ValueError, match="missing required parameters"):
        glue.render(expand=["param"])


def test_render_warns_on_undefined_filters():
    glue = CypherGlue()
    glue.register(Snippet(name="x", defines=["a"]))

    with pytest.raises(
        ValueError, match="Required variable\(s\) not defined by any Snippet: undeffy"
    ):
        glue.render(expand=["x"], filter_by={"undeffy.key": {"$eq": 1}})


def test_render_snippet_dependency_resolution():
    glue = CypherGlue()
    glue.register(Snippet("a", "MATCH (x:X)", defines=["x"], returns=["x"]))
    glue.register(
        Snippet("b", "MATCH (x)-->(y:Y)", defines=["y"], requires=["x"], returns=["y"])
    )

    query, _ = glue.render(expand=["y"])
    assert query == "MATCH (x:X)\nMATCH (x)-->(y:Y)\nRETURN DISTINCT\n    x,\n    y"


def test_render_snippet_with_star_return_includes_defined_vars():
    """When a Snippet returns a star, all defined variables rendered into RETURN clause"""
    glue = CypherGlue()
    glue.register(Snippet(name="star", query="MATCH (s)", defines=["s"], returns=["*"]))
    query, _ = glue.render(expand=["star"])
    assert query == "MATCH (s)\nRETURN DISTINCT\n    s"


def test_select_snippets_all_keyword():
    glue = CypherGlue()
    glue.register(Snippet("a"))
    glue.register(Snippet("b"))
    result = glue._select_snippets(["all"], [], [])
    assert len(result) == 2


def test_select_snippet_with_conflicting_vars_warns():
    glue = CypherGlue()
    glue.register(Snippet(name="A", defines=["x"]))
    glue.register(Snippet(name="B", defines=["x"]))

    # Variable 'x' is defined by both Snippets, should emit a Warning
    with pytest.warns(RuntimeWarning, match="Multiple Snippet define variable 'x'"):
        glue._select_snippets(["x"], [], [])


def test_select_snippet_missing_var_raises():
    glue = CypherGlue()
    with pytest.raises(ValueError, match="not defined by any Snippet"):
        glue._select_snippets(["missing"], [], [])


@pytest.mark.parametrize("initial_params", [{}, {"uid": "0123"}])
def tests_render_receives_params(initial_params):
    """Snippet.render receives the params argument of CypherGlue.render"""
    render_params = {}

    class Snip(Snippet):
        name = "snip"

        def render(self, params=None):
            nonlocal render_params
            render_params.update(params)
            return self.query, {}, self.returns

    glue = CypherGlue()
    glue.register(Snip)
    query, params = glue.render(expand=["all"], params=initial_params)
    assert params == initial_params
    assert render_params == initial_params


@pytest.mark.parametrize(
    "initial_params", [{}, {"uid": "0123"}, {"queen": "Elizabeth"}]
)
def tests_render_extends_params(initial_params):
    """Snippet.render can extend query params returned by CypherGlue.render"""
    glue = CypherGlue()

    @glue.register("hms")
    class Snip(Snippet):
        def render(self, params=None):
            return self.query, {"queen": "Victoria"}, self.returns

    expected = initial_params.copy()
    expected.update({"queen": "Victoria"})

    query, params = glue.render(expand=["all"], params=initial_params)
    assert len(params) == len(initial_params) + int("queen" not in initial_params)
    assert params == expected
