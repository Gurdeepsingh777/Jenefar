from jenefar.core.planner import Planner

def test_python_plan():
    assert Planner().plan("debug my Python script").agent=="python"

def test_security_plan():
    assert Planner().plan("explain nmap").agent=="cybersecurity"

def test_robotics_plan():
    assert Planner().plan("ESP32 servo sensor").agent=="robotics"
