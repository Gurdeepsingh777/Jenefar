from jenefar.agents.coding.repository_agent import RepositoryAgent

def test_repository_agent_matches_github_requests():
    agent = RepositoryAgent()
    assert agent.can_handle("analyze this GitHub repository")

def test_repository_agent_matches_change_planning():
    agent = RepositoryAgent()
    assert agent.can_handle("plan a refactor for this codebase")
