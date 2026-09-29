from jenefar.core.task_plan import HierarchicalTaskPlanner


def test_gui_vision_plan_requires_observe_action_verify():
    plan = HierarchicalTaskPlanner().build(
        "click the Submit button on screen",
        "semantic_gui",
        "gui_vision",
    )
    assert [step.id for step in plan.steps] == ["observe", "act", "verify"]
    assert all(step.verification or step.requires_action for step in plan.steps)
