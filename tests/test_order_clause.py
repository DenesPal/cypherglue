"""Tests order and pagination clauses"""

import pytest

from cypherglue import CypherGlue


@pytest.mark.parametrize(
    "order_by, available, skip, limit, expected",
    [
        ({"a.x": "ASC"}, {"a"}, 0, 0, "WITH DISTINCT * ORDER BY a.x ASC"),
        (
            {"b.y": "DESC"},
            {"b"},
            5,
            10,
            "WITH DISTINCT * ORDER BY b.y DESC SKIP 5 LIMIT 10",
        ),
        ({"d.q": "ASC"}, {"x"}, 0, 0, None),  # var not available
    ],
)
def test_render_order_clause(order_by, available, skip, limit, expected):
    result = CypherGlue._render_order_pagination_clauses(
        order_by, available, skip, limit
    )
    assert result == expected


def test_render_order_clause_invalid_direction_raises():
    with pytest.raises(ValueError, match="Invalid order direction"):
        CypherGlue._render_order_pagination_clauses({"a.b": "UP"}, {"a"}, 0, 0)
