from __future__ import annotations

from codecortex.context.slicing import AstContextSlicer
from codecortex.core.models import AgentRequest, Capability
from codecortex.distributed.cluster import ClusterCoordinator
from codecortex.distributed.graph_store import DistributedGraphStore
from codecortex.evaluation.retrieval_quality import (
    RetrievalQualityBenchmark,
    RetrievalQualityCase,
)
from codecortex.evaluation.scale import RepositoryScaleBenchmark
from codecortex.feedback import AgentFeedbackStore
from codecortex.indexing.graph import GraphNode, ProjectGraph
from codecortex.router import AdaptiveRouter
from codecortex.workspace.federation import MultiRepositoryWorkspace


def test_feedback_adjusts_router_scores(tmp_path) -> None:
    feedback = AgentFeedbackStore(tmp_path / "feedback.db")
    for _ in range(4):
        feedback.record("explain", Capability.REPOSITORY, True, 20)
        feedback.record("locate", Capability.SYMBOLS, False, 20)
    router = AdaptiveRouter(feedback=feedback)
    plan = router.route(AgentRequest(query="explain architecture"))
    scores = {item.capability: item.score for item in plan.scores}
    assert feedback.routing_adjustment(Capability.REPOSITORY) > 0
    assert feedback.routing_adjustment(Capability.SYMBOLS) < 0
    assert scores[Capability.REPOSITORY] > scores[Capability.SYMBOLS]


def test_ast_context_slicer_returns_complete_symbol_not_neighbor(tmp_path) -> None:
    path = tmp_path / "service.py"
    path.write_text(
        "def alpha():\n"
        "    value = 1\n"
        "    return value\n\n"
        "def beta():\n"
        "    secret = 2\n"
        "    return secret\n",
        encoding="utf-8",
    )
    sliced = AstContextSlicer(tmp_path).slice_symbol(
        path, "alpha", 1, max_tokens=100
    )
    assert "def alpha" in sliced
    assert "return value" in sliced
    assert "secret = 2" not in sliced


def test_retrieval_quality_reports_recall_precision_and_mrr() -> None:
    benchmark = RetrievalQualityBenchmark(
        [RetrievalQualityCase("one", "auth", ("expected",), limit=3)]
    )
    report = benchmark.run(lambda query, limit: ["wrong", "expected", "other"])
    result = report.results[0]
    assert result.recall == 1.0
    assert result.precision == 1 / 3
    assert result.reciprocal_rank == 0.5


def test_scale_benchmark_marks_actual_targets_only(tmp_path) -> None:
    for index in range(3):
        (tmp_path / f"f{index}.py").write_text("x = 1\n", encoding="utf-8")
    report = RepositoryScaleBenchmark((2, 100)).run(tmp_path)
    assert report.samples[0].reached is True
    assert report.samples[0].observed_files == 2
    assert report.samples[1].reached is False
    assert report.samples[1].observed_files == 3


def test_distributed_graph_store_persists_revisions(tmp_path) -> None:
    store = DistributedGraphStore(tmp_path / "graphs.db")
    graph = ProjectGraph(
        nodes=[GraphNode(id="file:a.py", kind="file", name="a.py", path="a.py")],
        edges=[],
    )
    store.replace("repo", "r1", graph)
    assert store.latest_revision("repo") == "r1"
    assert store.load("repo").nodes[0].id == "file:a.py"
    assert store.repositories() == ("repo",)


def test_cluster_coordinator_shards_work_and_publishes_graph(tmp_path) -> None:
    cluster = ClusterCoordinator(tmp_path / "cluster")
    cluster.workers.register_worker("indexer", ("index",))
    cluster.workers.register_worker("retriever", ("retrieve",))
    tasks = cluster.schedule_index(
        "repo", ["a", "b", "c"], "r1", shard_size=2
    )
    assert len(tasks) == 2
    retrieval = cluster.schedule_retrieval("auth", "repo", "r1")
    assert retrieval.kind == "retrieve"
    graph = ProjectGraph(nodes=[GraphNode(id="x", kind="file", name="x")])
    cluster.publish_graph("repo", "r1", graph)
    status = cluster.status()
    assert status.workers == 2
    assert status.queued == 3
    assert status.graph_repositories == 1


def test_cross_repo_dependency_edges_are_resolved(tmp_path) -> None:
    app = tmp_path / "app"
    shared = tmp_path / "shared"
    app.mkdir()
    (shared / "shared").mkdir(parents=True)
    (app / "main.py").write_text(
        "import shared.util\n\ndef run():\n    return 1\n",
        encoding="utf-8",
    )
    (shared / "shared" / "util.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )
    workspace = MultiRepositoryWorkspace()
    workspace.add_repository("app", app)
    workspace.add_repository("shared", shared)
    workspace.refresh()
    graph = workspace.federated_graph()
    edges = [edge for edge in graph.edges if edge.kind == "cross_repo_dependency"]
    assert edges
    assert any(edge.metadata.get("source_repository") == "app" for edge in edges)
