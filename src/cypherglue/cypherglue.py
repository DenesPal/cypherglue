import itertools
import re
import textwrap
import warnings
from collections.abc import Mapping, Set
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Iterable, Sequence, Type


# Cypher comparator operator aliases
CYPHER_COMPARATOR_OPERATOR_ALIAS_MAP = {
    "$eq": "=",
    "$ne": "<>",
    "$gt": ">",
    "$lt": "<",
    "$in": "IN",
}


@dataclass(frozen=True)
class Extends:
    """Return-element for extending a node/structure with `name`, ex.: "RETURN name { elements.... } AS key"."""

    name: str
    elements: "ReturnElements"


@dataclass(frozen=True)
class Verbatim:
    """Verbatim Cypher expression

    A ReturnElement for returning a literal key, ex.: `(".*", Verbatim)` or `(".*", Verbatim(".*"))`,
    renders as ".*" only.
    A filter expression: `filter_by={"movie": Verbatim("NOT (movie)<-[:REVIEWED]-()")}`.
    """

    expression: str

    def __str__(self):
        return self.expression


ReturnElement = (
        Extends
        | Verbatim
        | Sequence[str | tuple[str, "ReturnElement"]]
        | Mapping[str, "ReturnElement"]
        | Any
)
ReturnElements = Sequence[str | tuple[str, ReturnElement]] | Mapping[str, ReturnElement]

# to split at dots: ".foo.bar..baz" to ['.foo', 'bar', '.baz']
_CHOP_SPECKLED_PATH = re.compile(r"(?<!^)(?<!\.)\.")


@dataclass(frozen=True)
class Snippet:
    """
    Represents a modular Cypher query fragment.

    Attributes:
        name (str): The unique name of the snippet (within a QueryBuilder instance, the `@qb.register("name")` decorator overrides this.).
        query (str): The Cypher query fragment. May contain format-style substitutions when used together with `labels`.
        returns (tuple[str | tuple[str, str]]): Fragments for the RETURN clause: see ReturnElements.
        labels (Mapping[str, str]): Optional mapping in case the query text requires format-style substitutions.
        requires (tuple[str, ...]): Cypher nodes/structures/variables this snippet depends on (consumes from other snippets).
        defines (tuple[str, ...]): Cypher nodes/structures/variables this snippet defines.
        parameters (tuple[str, ...]): Query parameters required by the snippet.
        always (bool): Always include this snippet in the rendered query.
        allow_filtering (bool): Allow injecting filtering statements after this snippet depending on defined variables.
        allow_pagination (bool): Always injecting pagination after this snippet ordering by defined variables.
    """

    name: str = ""
    query: str = ""
    returns: ReturnElements = tuple()
    labels: MappingProxyType[str, str] | None = None
    requires: frozenset[str] = field(default_factory=frozenset)
    defines: frozenset[str] = field(default_factory=frozenset)
    parameters: frozenset[str] = field(default_factory=frozenset)
    always: bool = False
    allow_filtering: bool = True
    allow_pagination: bool = True

    def __init__(
            self,
            name: str | None = None,
            query: str | None = None,
            *,
            returns: ReturnElements | None = None,
            labels: Mapping[str, str] | None = None,
            requires: Sequence[str] | None = None,
            defines: Sequence[str] | None = None,
            parameters: Sequence[str] | None = None,
            always: bool | None = None,
            allow_filtering: bool | None = None,
            allow_pagination: bool | None = None,
    ):
        """__init__ to preserve default values of class properties."""

        if name is None:
            name = getattr(self, "name", None)
        if name:
            object.__setattr__(self, "name", name)
        if not self.name:
            raise TypeError("Name must be specified.")

        # get the default query from (sub)class definition
        if query is None:
            query = getattr(self, "query", "")
        # Strip leading whitespace from triple-quoted strings
        if query:
            query = textwrap.dedent(query).strip()
            object.__setattr__(self, "query", query)

        if isinstance(returns, Mapping):
            object.__setattr__(self, "returns", MappingProxyType(returns))
        elif isinstance(returns, str):
            object.__setattr__(self, "returns", (returns,))
        elif isinstance(returns, (tuple, list)):
            object.__setattr__(self, "returns", tuple(returns))

        object.__setattr__(
            self,
            "requires",
            (
                frozenset(getattr(self, "requires", tuple()))
                if requires is None
                else frozenset(requires)
            ),
        )
        object.__setattr__(
            self,
            "defines",
            (
                frozenset(getattr(self, "defines", tuple()))
                if defines is None
                else frozenset(defines)
            ),
        )
        object.__setattr__(
            self,
            "parameters",
            (
                frozenset(getattr(self, "parameters", tuple()))
                if parameters is None
                else frozenset(parameters)
            ),
        )

        if labels is None:
            labels = getattr(self, "labels", None)
        object.__setattr__(
            self, "labels", None if labels is None else MappingProxyType(labels)
        )

        object.__setattr__(
            self,
            "always",
            getattr(self, "always", False) if always is None else bool(always),
        )
        object.__setattr__(
            self,
            "allow_filtering",
            (
                getattr(self, "allow_filtering", True)
                if allow_filtering is None
                else bool(allow_filtering)
            ),
        )
        object.__setattr__(
            self,
            "allow_pagination",
            (
                getattr(self, "allow_pagination", True)
                if allow_pagination is None
                else bool(allow_pagination)
            ),
        )

    def clone(self, **kwargs) -> "Snippet":
        """Return a new Snippet with some properties replaced."""
        return replace(self, **kwargs)

    def render(
            self, params: Mapping[str, Any] | None = None
    ) -> tuple[str, Mapping[str, Any], "ReturnElements"]:
        """Render the snippet's Cypher fragment, applying label substitutions."""
        # pylint: disable=unused-argument

        query = self.query
        if self.labels:
            # Substitute label placeholders like {LabelKey}
            query = query.format_map(self.labels)

        return query, {}, self.returns


class CypherGlue:
    """
    Builds complex Cypher queries from registered Snippet instances.
    """

    def __init__(self):
        self._snippets: dict[str, Snippet] = {}
        self._vars_to_snippet: dict[str, list[str]] = {}
        self._snippet_view = MappingProxyType(self._snippets)

    @property
    def snippets(self) -> dict[str, Snippet]:
        return self._snippet_view

    def register(self, snippet_or_name: str | Snippet | Type[Snippet]):
        """
        Registers a snippet instance or a Snippet subclass, which it instantiates.
        It also can be used as a decorator on subclasses of Snippet, prividing name as an optional positional argument.
        Order of registration determines building order.
        """

        # Does the registration
        def _register(snippet):
            if snippet.name in self._snippets:
                raise ValueError(
                    f"Snippet with name '{snippet.name}' is already registered."
                )

            self._snippets[snippet.name] = snippet

            for var in snippet.defines:
                self._vars_to_snippet.setdefault(var, []).append(snippet)

        # Decorator as `@qb.register(name)` on Snippet subclass
        if isinstance(snippet_or_name, str):

            def decorator(cls):
                if not isinstance(cls, type) or not issubclass(cls, Snippet):
                    raise TypeError("Decorator must be applied to a Snippet subclass.")

                instance = cls(name=snippet_or_name)
                _register(instance)

                return cls

            return decorator

        # Method call as `qb.register(snippet)` on Snippet instance
        if isinstance(snippet_or_name, Snippet):
            snippet = snippet_or_name

        # Decorator as `@qb.register` on Snippet subclass
        elif isinstance(snippet_or_name, type) and issubclass(snippet_or_name, Snippet):
            snippet = snippet_or_name()  # Instantiate the class

        else:
            raise TypeError(
                "Argument must be a Snippet instance or a Snippet subclass."
            )

        _register(snippet)

        return snippet_or_name  # Return the original class for decorator to work

    def render(
            self,
            expand: Iterable[str] | None = None,
            params: Mapping[str, Any] | None = None,
            filter_by: Mapping[str, Mapping[str, Any]] | None = None,
            order_by: Iterable[str] | Iterable[tuple[str, str]] | None = None,
            skip: int = 0,
            limit: int = 0,
    ) -> tuple[str, dict[str, Any]]:
        """
        Builds the Cypher query and parameters.

        Args:
            expand (Iterable[str]): A list of snippet names or variable names to expand.
            params (Mapping[str, Any]): The parameters for the query.
            filter_by (Optional[Mapping[str, Mapping[str, Any]]]): Filtering expressions.
            order_by (Optional[Union[Iterable[str], Iterable[Tuple[str, str]]]]): Ordering expressions.
            skip (Optional[int]): The number of results to skip for pagination.
            limit (Optional[int]): The maximum number of results to return.

        Returns:
            tuple[str, dict[str, Any]]: The generated Cypher query and its parameters.
        """
        expand = dict.fromkeys(expand or []).keys()
        params = MappingProxyType(params or {})
        filter_by = filter_by or {}
        if isinstance(order_by, Mapping):
            raise TypeError(
                "order_by mapping type is not supported"
            )  # due to unstable order of elements
        if isinstance(order_by, set):
            raise TypeError(
                "order_by set type is not supported"
            )  # due to unstable order of elements
        order_by = dict(
            (item, "ASC") if isinstance(item, str) else (item[0], item[1].upper())
            for item in order_by or []
        )

        query_parts: list[str] = []
        final_params = dict(params)

        selected_snippets = self._select_snippets(
            expand,
            filter_keys=filter_by.keys(),
            order_keys=dict.fromkeys(
                item[0] if isinstance(item, tuple) else item for item in order_by
            ).keys(),
        )

        if not selected_snippets:
            raise RuntimeError("No snippets selected, provide expand parameter")

        # Build query string

        available_vars: set[str] = set()
        remaining_filters = dict(filter_by)
        return_elements: list[str | tuple[str, str]] = []

        for snippet in selected_snippets:
            if missing_params := set(snippet.parameters) - set(final_params.keys()):
                raise ValueError(
                    f"Snippet '{snippet.name}' is missing required parameters: {missing_params}"
                )

            # Render query snippet, receiving updated params and expressions for RETURN clause
            query, params_update, returns = snippet.render(params)
            if query:
                # include rendered query piece
                query_parts.append(query)
                # query variables defined by the query fragment
                available_vars.update(snippet.defines)
            # added/updated query parameters
            final_params.update(params_update)

            # Collect return expressions related to the fragment
            if "*" in returns:
                # return all resolved query variables
                return_elements.extend(snippet.defines)
            if isinstance(returns, Mapping):
                returns_it = ((k, v) for k, v in returns.items() if k != "*")
            else:
                returns_it = filter(lambda x: x and x != "*", returns)
            return_elements.extend(returns_it)

            # Append the WHERE clause if some filter variables are already defined
            if snippet.allow_filtering and remaining_filters:
                filter_clause, filter_params = self._render_filter_clauses(
                    remaining_filters, available_vars
                )
                if filter_clause:
                    query_parts.append(filter_clause)
                    final_params.update(filter_params)

            # Append ORDER BY, SKIP and LIMIT clauses if applicable (but only if done with filtering)
            if (
                    not remaining_filters
                    and snippet.allow_pagination
                    and (order_by or skip or limit)
            ):
                order_clause = self._render_order_pagination_clauses(
                    order_by, available_vars, skip, limit
                )
                if order_clause:
                    query_parts.append(order_clause)
                    # the ordering-pagination clause has been added
                    order_by = None
                    skip, limit = None, None

        # Apply remaining filters
        if remaining_filters:
            filter_clause, filter_params = self._render_filter_clauses(
                remaining_filters, None
            )
            if filter_clause:
                query_parts.append(filter_clause)
                final_params.update(filter_params)

            if remaining_filters:
                warnings.warn(
                    f"Some query variables used in filters are probably not defined: {', '.join(remaining_filters.keys())}",
                    RuntimeWarning,
                )

        # Add ordering-pagination clause if not added before
        if order_by or skip or limit:
            if order_clause := self._render_order_pagination_clauses(
                    order_by, available_vars, skip, limit
            ):
                query_parts.append(order_clause)

        # Construct the RETURN statement
        if return_elements:
            query_parts.append(self.render_return_clause(return_elements))

        # Join query parts and return with parameters
        full_query = "\n".join(filter(None, query_parts))
        return full_query, final_params

    def _select_snippets(
            self,
            expand: Iterable[str],
            filter_keys: Iterable[str],
            order_keys: Iterable[str],
    ) -> tuple[Snippet, ...]:
        if "all" in expand:
            # requested rendering of all snippets
            return tuple(self._snippets.values())

        # selected_snippets = set() # snippets selected
        # defined_vars = set() # variables defined by a selected snippet

        # 1. Gather all variable names that need to be defined
        required_vars = set(name for name in expand if name not in self._snippets)

        for var in filter_keys:
            required_vars.add(var.split(".")[0])

        for var in order_keys:
            required_vars.add(var.split(".")[0])

        # 2. Find all snippets that are needed directly or always need to be rendered
        selected_snippet_names = set(
            name for name, snippet in self._snippets.items() if snippet.always
        )

        # Snippets requested by name
        for name in expand:
            if name in self._snippets:
                selected_snippet_names.add(name)

        # 3. Resolve all dependencies
        # Gather required and defined variables to see what is missing
        defined_vars = set()
        for name in selected_snippet_names:
            snippet = self._snippets[name]
            defined_vars.update(snippet.defines)
            required_vars.update(snippet.requires)

        # Keeps looking for missing variables until a required Snippet is found
        while missing_vars := required_vars - defined_vars:
            found_snippets_names = set()

            # Look up snippets defining missing variables
            for var in missing_vars:
                if snippets := self._vars_to_snippet.get(var):
                    if len(snippets) > 1:
                        warnings.warn(
                            f"Multiple Snippet define variable '{var}', picking first registered.",
                            RuntimeWarning,
                        )
                    found_snippets_names.add(snippets[0].name)

            if not found_snippets_names:
                # No more Snippets found for variables, resolving has failed
                raise ValueError(
                    f"Required variable(s) not defined by any Snippet: {', '.join(missing_vars)}"
                )

            # Update required and defined variables
            for snippet_name in found_snippets_names:
                snippet = self._snippets[snippet_name]
                selected_snippet_names.add(snippet.name)
                defined_vars.update(snippet.defines)
                required_vars.update(snippet.requires)

        # 4. Return selected snippets in order of registration
        return tuple(
            snippet
            for snippet in self._snippets.values()
            if snippet.name in selected_snippet_names
        )

    @staticmethod
    def _render_filter_clauses(
            filter_by: dict[str, Mapping[str, Any]], available_vars: set[str] | None
    ) -> tuple[str | None, dict | None]:
        """
        Constructs a WHERE clause for filters whose variable is available,
        or all if `available_vars` is None.
        Updates filter_by mapping in-place by removing used filter keys.
        """

        clauses = []
        params = {}

        for filter_key, expression in list(filter_by.items()):
            i = 0

            var_name = filter_key.split(".")[0]
            if available_vars is not None and var_name not in available_vars:
                continue  # Variable not yet available for filtering

            for op, param_value in expression.items():
                cypher_op = CYPHER_COMPARATOR_OPERATOR_ALIAS_MAP.get(op, op)

                param_name = f"_filter_{filter_key.replace('.', '__')}_{i}"
                clauses.append(f"{filter_key} {cypher_op} ${param_name}")
                params[param_name] = param_value

                filter_by.pop(filter_key, None)

        if not clauses:
            return None, None

        return f"WHERE {' AND '.join(clauses)}", params

    @staticmethod
    def _render_order_pagination_clauses(
            order_by: Mapping[str, str],
            available_vars: set[str] | None,
            skip: int,
            limit: int,
    ) -> str | None:
        """Constructs an ORDER BY clause if all required variables are available or `available_vars` is None."""

        if available_vars is not None:
            required_vars = set(key.split(".", 1)[0] for key in order_by.keys())
            if not required_vars.issubset(available_vars):
                # Not all variables are available yet
                return None

        order_clauses = []

        for key, direction in order_by.items():
            if direction not in {"ASC", "DESC"}:
                raise ValueError(f"Invalid order direction for '{key}': '{direction}'")

            order_clauses.append(f"{key} {direction}")

        query_parts = []

        if order_clauses or skip or limit:
            query_parts.append("WITH DISTINCT *")

        if order_clauses:
            query_parts.append("ORDER BY")
            query_parts.append(", ".join(order_clauses))

        if skip:
            # TODO add SKIP to query params
            query_parts.append(f"SKIP {skip:d}")

        if limit:
            # TODO add LIMIT to query params
            query_parts.append(f"LIMIT {limit:d}")

        return " ".join(query_parts)

    @staticmethod
    def render_return_clause(items: ReturnElements, *, distinct: bool = True) -> str:
        """Renders a Cypher RETURN clause from a structured representation.

        Supports various input formats to generate complex RETURN clauses with nested objects,
        property extensions, and value expressions.

        Args:
            items: Input structure defining the RETURN clause elements. Can be either:
                - Sequence of return elements (tuple or list)
                - Mapping of aliases to return elements
            distinct: When True, adds DISTINCT keyword to the RETURN clause to remove duplicate rows.
                Defaults to True.

        Return elements can be:
            - String literals: Direct expressions like "*" or property access
            - Tuples: (alias, value) pairs where value can be:
                - String expression
                - Nested sequence for object definitions
                - Mapping for object properties
            - Mappings: Direct object property definitions

        Examples:
            # Basic value aliasing
            >>> render_return_clause([("details", "value_node"), "root.uid"])
            'RETURN DISTINCT
                value_node AS details,
                root.uid'

            # Object with properties
            >>> render_return_clause([("report", {"lazy": False, "name": "'Kitty'", "legs": 4.2, "mouse": None})])
            'RETURN DISTINCT
                {
                    lazy: false,
                    name: 'Kitty',
                    legs: 4.2,
                    mouse: null
                } AS report'

            # Nested objects with property extensions
            >>> render_return_clause([
            ...     ("script", ("script_value", (
            ...         ".*",
            ...         ("uid", "script_root.uid"),
            ...         ("version", ("script_version", (
            ...             ".status",
            ...             ".version"
            ...         )))
            ...     )))
            ... ])
            'RETURN DISTINCT
                script_value {
                    .*,
                    uid: script_root.uid,
                    version: script_version {
                        .status,
                        .version
                    }
                } AS script'

        # Amending existing objects
        >>> render_return_clause([
        ...     ("script", ("script_value", (".*",))),
        ...     ("script.version", ("script_version", (".status",))),
        ...     ("script.version.amendment", {"amended": True})
        ... ])
        'RETURN DISTINCT
            script_value {
                .*,
                version: script_version {
                    .status,
                    amendment: {
                        amended: true
                    }
                }
            } AS script'

        Returns:
            str: Formatted Cypher RETURN clause string
        """

        def to_str(value: any) -> str:
            """Renders value to a Cypher literal string."""
            if value is None:
                return "null"
            if isinstance(value, str):
                return value
            if isinstance(value, bool):
                return str(value).lower()
            if isinstance(value, Sequence):
                return f"[{', '.join(map(to_str, value))}]"
            if isinstance(value, Set):
                return f"{{{', '.join(map(to_str, value))}}}"
            if isinstance(value, Mapping):
                value = (f"{str(k)}: {to_str(v)}" for k, v in value.items())
                return f"{{{', '.join(value)}}}"
            return str(value)

        def render(
                items,
                level: int = 1,
                indent: int = 4,
                path: str = "",
                amendments: Mapping | None = None,
        ) -> list[str]:
            lines: list[str] = []
            spacing = " " * indent * level

            l = len(items)
            if isinstance(items, Mapping):
                items = items.items()

            if amendments and path and (amend_items := amendments.get(path)):
                items = itertools.chain(items, amend_items)
                l += len(amend_items)

            for i, item in enumerate(items, 1):
                is_last_item = i == l
                comma = "" if is_last_item else ","

                if isinstance(item, tuple):
                    if not item:
                        continue

                    key, value = item
                    embed, extends = None, ""

                    # if value is tuple/sequence/mapping
                    if isinstance(value, (Mapping, tuple)):
                        embed = value

                    # if extending a node/structure
                    elif isinstance(value, Extends):
                        embed = value.elements
                        extends = f"{value.name} "

                    # embeddable object/sub-document
                    if embed:
                        subpath = f"{path}.{key}"

                        # outer scope, "{ object... } AS name,"
                        if level == 1:
                            lines.append(f"{spacing}{extends}{{")
                            lines.extend(
                                render(
                                    embed,
                                    level=level + 1,
                                    indent=indent,
                                    path=subpath,
                                    amendments=amendments,
                                )
                            )
                            lines.append(f"{spacing}}} AS {key}{comma}")

                        # in an object: "property: { object... },"
                        else:
                            lines.append(f"{spacing}{key}: {extends}{{")
                            lines.extend(
                                render(
                                    embed,
                                    level=level + 1,
                                    indent=indent,
                                    path=subpath,
                                    amendments=amendments,
                                )
                            )
                            lines.append(f"{spacing}}}{comma}")

                    # inheriting an object/structure without value and alias, ex. "*", ".*", or ".uid", from tuple/mapping
                    elif value is Verbatim:
                        lines.append(f"{spacing}{key}{comma}")
                    elif isinstance(value, Verbatim):
                        lines.append(f"{spacing}{value!s}{comma}")

                    # simple "key: value" pair
                    elif level == 1:
                        # outer scope: "expression AS name,"
                        lines.append(f"{spacing}{to_str(value)} AS {key}{comma}")
                    else:
                        # in an object: "property: expression,"
                        lines.append(f"{spacing}{key}: {to_str(value)}{comma}")

                # string literal, outside mapping or key/value tuple, ex.: "*", ".*", or ".uid"
                else:
                    item = to_str(item)
                    lines.append(f"{spacing}{item}{comma}")

            return lines

        if isinstance(items, Mapping):
            items = items.items()  # ease iterations on different types

        # separate amendments
        amendments = {}
        remove_items_idx = set()

        for i, item in enumerate(items):
            if isinstance(item, str):
                key, values = item, None
            elif isinstance(item, Verbatim):
                continue
            else:
                key, *values = item

            if values and (values[0] is Verbatim or isinstance(values[0], Verbatim)):
                # keep rendering `{"root.uid": Verbatim}` to "root.uid," literal
                continue

            # splits ".foo.bar..baz" to ['.foo', 'bar', '.baz']
            keys = _CHOP_SPECKLED_PATH.split(key)

            if len(keys) > 1:
                path = f".{'.'.join(keys[:-1])}"
                if values:
                    # amendment with elements ex.: ("node.details", {"uid": 1})
                    amendments.setdefault(path, []).append((keys[-1], *values))
                else:
                    # amendment was a pure string like: "node.details.uid"
                    amendments.setdefault(path, []).append(keys[-1])
                remove_items_idx.add(i)

        # remove amendments items
        if remove_items_idx:
            # can't forward as iterator, because render() does a len() call on it
            items = [item for i, item in enumerate(items) if i not in remove_items_idx]

        # render output lines recursively
        lines: list[str] = render(items, amendments=amendments)

        # return the final string
        if lines:
            lines.insert(0, ("RETURN DISTINCT" if distinct else "RETURN"))
            return "\n".join(lines)
        return ""
