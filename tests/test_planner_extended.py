from jenefar.core.planner import Planner


def test_planner_routes_local_python_task():
    plan = Planner().plan("/home/jenefar/Document/Tools/example.py check this file and fix the error")
    assert plan.agent == "local_development"


def test_planner_routes_media_task():
    plan = Planner().plan("mujhe YouTube par ye song play karo")
    assert plan.agent == "automation"


def test_planner_routes_kali_task():
    plan = Planner().plan("Kali me nmap use karo")
    assert plan.agent == "kali"
