"""Filters must be rendered as valid Cypher after any kind of snippet.

Cypher only accepts `WHERE` directly after `MATCH`, `OPTIONAL MATCH` or `WITH`, and once per clause. After any other
clause (ex. `UNWIND`, `CALL`), or after a snippet that already ends in its own `WHERE`, a filter needs a `WITH` in
front: `WITH * WHERE ...`.

The expected queries below are valid Cypher (checked with `EXPLAIN` on Neo4j 5.26). The tests fail while CypherGlue
renders a bare `WHERE`, which is a syntax error in these positions.
"""

from textwrap import dedent

import pytest

from cypherglue import CypherGlue, Snippet


@pytest.fixture(name="glue")
def fixture_glue() -> CypherGlue:
    """Fixture returns a query with a `movie` snippet that other snippets build upon"""

    glue = CypherGlue()
    glue.register(
        Snippet(
            "movie",
            "MATCH (movie:Movie)",
            defines=["movie"],
            returns={"movie": "movie"},
            always=True,
        )
    )
    return glue


def test_renders_filter_after_snippet_ending_with_where(glue):
    """CypherGlue renders `WITH * WHERE` for a filter after a snippet which already ends with its own WHERE"""
    glue.register(
        Snippet(
            "writer",
            "MATCH (movie)<-[:WROTE]-(writer:Person) WHERE writer.born > 1900",
            requires=["movie"],
            defines=["writer"],
        )
    )

    query, params = glue.render(
        expand=["writer"], filter_by={"writer.name": {"$eq": "Nancy Meyers"}}
    )

    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        MATCH (movie)<-[:WROTE]-(writer:Person) WHERE writer.born > 1900
        WITH * WHERE writer.name = $_filter_writer__name_0
        RETURN DISTINCT
            movie AS movie
    """
        ).strip()
    )
    assert params == {"_filter_writer__name_0": "Nancy Meyers"}


def test_renders_filter_after_unwind(glue):
    """CypherGlue renders `WITH * WHERE` for a filter on a variable defined by UNWIND"""
    glue.register(
        Snippet("tag", "UNWIND movie.tags AS tag", requires=["movie"], defines=["tag"])
    )

    query, params = glue.render(expand=["tag"], filter_by={"tag": {"$eq": "drama"}})

    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        UNWIND movie.tags AS tag
        WITH * WHERE tag = $_filter_tag_0
        RETURN DISTINCT
            movie AS movie
    """
        ).strip()
    )
    assert params == {"_filter_tag_0": "drama"}


def test_renders_filter_after_call_subquery(glue):
    """CypherGlue renders `WITH * WHERE` for a filter on a variable returned by a CALL subquery"""
    glue.register(
        Snippet(
            "reviews",
            """
            CALL (movie) {
              MATCH (movie)<-[:REVIEWED]-(review)
              RETURN count(review) AS reviews
            }
            """,
            requires=["movie"],
            defines=["reviews"],
        )
    )

    query, params = glue.render(expand=["reviews"], filter_by={"reviews": {"$gt": 3}})

    assert (
        query
        == dedent(
            """
        MATCH (movie:Movie)
        CALL (movie) {
          MATCH (movie)<-[:REVIEWED]-(review)
          RETURN count(review) AS reviews
        }
        WITH * WHERE reviews > $_filter_reviews_0
        RETURN DISTINCT
            movie AS movie
    """
        ).strip()
    )
    assert params == {"_filter_reviews_0": 3}
