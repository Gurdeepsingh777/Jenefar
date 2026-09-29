from jenefar.core.planner import Planner


def test_planner_routes_repository_requests():
    plan = Planner().plan("analyze the GitHub repository architecture")
    assert plan.agent == "repository"
    assert plan.confidence > 0.9


def test_planner_routes_python_requests():
    plan = Planner().plan("write a FastAPI Python endpoint")
    assert plan.agent == "python"


def test_planner_falls_back_to_research():
    plan = Planner().plan("what is the history of computers?")
    assert plan.agent == "research"
    assert plan.confidence < 0.6
