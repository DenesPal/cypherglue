"""Test filter expressions"""

import pytest

from cypherglue import CypherGlue


@pytest.mark.parametrize(
    "filter_by, available_vars, expected_clause, expected_params",
    [
        (  # simple filter expression
            {"person.age": {"$gt": 30}},
            {"person"},
            "WHERE person.age > $_filter_person__age_0",
            {"_filter_person__age_0": 30},
        ),
        (  # filter variable is not (yet) available
            {"movie.title": {"$eq": "Alice"}},
            {"director", "studio"},
            None,
            None,
        ),
        (  # only some filter variables are available
            {"director.age": {"$gt": 36}, "movie.title": {"$eq": "Hello"}},
            {"person", "movie"},
            "WHERE movie.title = $_filter_movie__title_0",
            {"_filter_movie__title_0": "Hello"},
        ),
        (  # when remaining filters rendered at the end regardless of the availability of variables
            {"movie.title": {"$in": ["Hello", "Alice"]}},
            None,
            "WHERE movie.title IN $_filter_movie__title_0",
            {"_filter_movie__title_0": ["Hello", "Alice"]},
        ),
    ],
)
def test_render_filter_clauses(
    filter_by, available_vars, expected_clause, expected_params
):
    filter_by = dict(filter_by)  # filter_by argument gets mutated
    clause, params = CypherGlue._render_filter_clauses(filter_by, available_vars)
    assert clause == expected_clause
    assert params == expected_params


@pytest.mark.parametrize(
    "filter_key",
    ["movie.title = '' OR 1=1 //", "movie title", "movie.", "1movie", "movie-title"],
)
def test_render_filter_clauses_invalid_key_raises(filter_key):
    with pytest.raises(ValueError, match="Invalid filter key"):
        CypherGlue._render_filter_clauses({filter_key: {"$eq": 1}}, None)


@pytest.mark.parametrize("op", ["= 1 OR true OR movie.x =", "$nope", "IS NULL"])
def test_render_filter_clauses_invalid_operator_raises(op):
    with pytest.raises(ValueError, match="Invalid filter operator"):
        CypherGlue._render_filter_clauses({"movie.title": {op: 1}}, None)


@pytest.mark.parametrize(
    "op",
    [
        "=",
        "<>",
        ">",
        "<",
        ">=",
        "<=",
        "=~",
        "IN",
        "STARTS WITH",
        "ENDS WITH",
        "CONTAINS",
    ],
)
def test_render_filter_clauses_accepts_operator(op):
    clause, _ = CypherGlue._render_filter_clauses({"movie.title": {op: 1}}, None)
    assert clause == f"WHERE movie.title {op} $_filter_movie__title_0"
