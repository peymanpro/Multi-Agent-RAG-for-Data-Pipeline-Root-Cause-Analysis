from pipeline_rca.lineage import LineageGraph
from pipeline_rca.models import LineageEdge


def test_downstream_traversal_is_stable_and_cycle_safe() -> None:
    graph = LineageGraph(
        (
            LineageEdge("raw_orders", "stg_orders"),
            LineageEdge("stg_orders", "fact_orders"),
            LineageEdge("fact_orders", "sales_report"),
            LineageEdge("stg_orders", "quality_checks"),
            LineageEdge("quality_checks", "stg_orders"),
        )
    )

    assert graph.downstream_of("raw_orders") == (
        "stg_orders",
        "fact_orders",
        "quality_checks",
        "sales_report",
    )
    assert graph.downstream_of("missing") == ()


def test_cycle_detection_returns_canonical_cycles() -> None:
    graph = LineageGraph(
        (
            LineageEdge("a", "b"),
            LineageEdge("b", "c"),
            LineageEdge("c", "a"),
        )
    )

    assert graph.cycles() == (("a", "b", "c"),)


def test_empty_graph_has_no_nodes_or_cycles() -> None:
    graph = LineageGraph(())

    assert graph.nodes == ()
    assert graph.cycles() == ()
