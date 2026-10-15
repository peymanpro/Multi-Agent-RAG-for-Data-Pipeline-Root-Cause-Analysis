"""Dependency-graph helpers for pipeline impact analysis."""

from collections import deque

from pipeline_rca.models import LineageEdge


class LineageGraph:
    """Cycle-safe directed graph for pipeline dependencies.

    Edges point from upstream producer to downstream consumer. Traversal returns nodes
    in stable breadth-first order.
    """

    def __init__(self, edges: tuple[LineageEdge, ...] | list[LineageEdge]) -> None:
        adjacency: dict[str, set[str]] = {}
        nodes: set[str] = set()
        for edge in edges:
            nodes.add(edge.upstream)
            nodes.add(edge.downstream)
            adjacency.setdefault(edge.upstream, set()).add(edge.downstream)
            adjacency.setdefault(edge.downstream, set())
        self._adjacency = {
            node: tuple(sorted(neighbors)) for node, neighbors in adjacency.items()
        }
        self._nodes = frozenset(nodes)

    @property
    def nodes(self) -> tuple[str, ...]:
        """All nodes represented by at least one lineage edge."""
        return tuple(sorted(self._nodes))

    def downstream_of(self, root: str, *, include_root: bool = False) -> tuple[str, ...]:
        """Return reachable downstream nodes in deterministic breadth-first order."""
        if root not in self._adjacency:
            return (root,) if include_root else ()

        visited = {root}
        queue = deque([root])
        result: list[str] = []

        while queue:
            current = queue.popleft()
            if current != root or include_root:
                result.append(current)
            for neighbor in self._adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return tuple(result)

    def cycles(self) -> tuple[tuple[str, ...], ...]:
        """Return canonical node cycles for detecting invalid dependency models."""
        state: dict[str, int] = {}
        stack: list[str] = []
        found: set[tuple[str, ...]] = set()

        def visit(node: str) -> None:
            state[node] = 1
            stack.append(node)
            for neighbor in self._adjacency[node]:
                if state.get(neighbor, 0) == 0:
                    visit(neighbor)
                elif state.get(neighbor) == 1:
                    start = stack.index(neighbor)
                    cycle = stack[start:]
                    if cycle:
                        rotations = [
                            tuple(cycle[index:] + cycle[:index])
                            for index in range(len(cycle))
                        ]
                        found.add(min(rotations))
            stack.pop()
            state[node] = 2

        for node in sorted(self._nodes):
            if state.get(node, 0) == 0:
                visit(node)

        return tuple(sorted(found))
