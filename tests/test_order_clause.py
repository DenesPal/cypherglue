"""Tests order and pagination clauses"""

import pytest

from cypherglue import CypherGlue


@pytest.mark.parametrize(
    "order_by, available, skip, limit, expected, expected_params",
    [
        ({"a.x": "ASC"}, {"a"}, 0, 0, "WITH DISTINCT * ORDER BY a.x ASC", {}),
        (
            {"b.y": "DESC"},
            {"b"},
            5,
            10,
            "WITH DISTINCT * ORDER BY b.y DESC SKIP $_skip LIMIT $_limit",
            {"_skip": 5, "_limit": 10},
        ),
        ({"d.q": "ASC"}, {"x"}, 0, 0, None, None),  # var not available
    ],
)
def test_render_order_clause(
    order_by, available, skip, limit, expected, expected_params
):
    clause, params = CypherGlue._render_order_pagination_clauses(
        order_by, available, skip, limit
    )
    assert clause == expected
    assert params == expected_params


@pytest.mark.parametrize(
    "skip, limit", [(-1, 0), (0, -5), ("10", 0), (0, 2.5), (True, 0)]
)
def test_render_order_clause_invalid_pagination_raises(skip, limit):
    with pytest.raises(ValueError, match="Invalid (skip|limit) value"):
        CypherGlue._render_order_pagination_clauses({}, None, skip, limit)


def test_render_order_clause_invalid_direction_raises():
    with pytest.raises(ValueError, match="Invalid order direction"):
        CypherGlue._render_order_pagination_clauses({"a.b": "UP"}, {"a"}, 0, 0)


@pytest.mark.parametrize(
    "key", ["a.b DESC, a.c", "a.b; MATCH (n) DETACH DELETE n", "a..b"]
)
def test_render_order_clause_invalid_key_raises(key):
    with pytest.raises(ValueError, match="Invalid order key"):
        CypherGlue._render_order_pagination_clauses({key: "ASC"}, None, 0, 0)
