from jenefar.core.task_plan import HierarchicalTaskPlanner


def test_task_planner_local_feature_is_bounded():
    plan = HierarchicalTaskPlanner().build(
        "fix this python script and test it",
        "local_development",
        "local_development",
    )
    assert plan.is_compound
    assert plan.steps[0].id == "inspect"
    assert plan.steps[-1].id == "report"
    assert "repair" in [step.id for step in plan.steps]
