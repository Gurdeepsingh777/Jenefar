from jenefar.agents.coding.python import PythonAgent
from jenefar.agents.research.research import ResearchAgent
from jenefar.core.router import AgentRouter


def test_router_selects_python():
    router = AgentRouter([PythonAgent(), ResearchAgent()])
    assert router.route("write a Python script").name == "python"


def test_router_honors_planned_agent():
    router = AgentRouter([PythonAgent(), ResearchAgent()])
    assert router.route(
        "tell me something",
        preferred_agent="python",
    ).name == "python"


def test_router_fallbacks_to_research():
    router = AgentRouter([PythonAgent(), ResearchAgent()])
    assert router.route("tell me something").name == "research"


def test_router_does_not_force_research_plan():
    router = AgentRouter([PythonAgent(), ResearchAgent()])
    assert router.route(
        "write a Python script",
        preferred_agent="research",
    ).name == "python"
