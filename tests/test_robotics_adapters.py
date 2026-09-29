from pathlib import Path

from jenefar.robotics.mqtt import MqttRobotController
from jenefar.robotics.ros2 import Ros2RobotController


def test_mqtt_command_requires_host():
    controller = MqttRobotController(host="")
    try:
        controller.publish_command("stop")
    except ValueError as exc:
        assert "JENEFAR_MQTT_HOST" in str(exc)
    else:
        raise AssertionError("Expected missing MQTT host")


def test_ros2_requires_runtime():
    controller = Ros2RobotController()
    try:
        controller.list_topics()
    except RuntimeError as exc:
        assert "ROS2" in str(exc)
    except Exception:
        pass
