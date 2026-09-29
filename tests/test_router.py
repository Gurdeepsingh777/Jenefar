from jenefar.core.router import AgentRouter
from jenefar.agents.coding.python import PythonAgent
from jenefar.agents.research.research import ResearchAgent

def test_router_selects_python():
    router=AgentRouter([PythonAgent(),ResearchAgent()])
    assert router.route("write a Python script").name=="python"

def test_router_fallbacks_to_research():
    router=AgentRouter([PythonAgent(),ResearchAgent()])
    assert router.route("tell me something").name=="research"
