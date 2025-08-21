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
