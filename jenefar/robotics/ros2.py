from __future__ import annotations

import os
from typing import Any


class Ros2RobotController:
    """Optional ROS2 adapter; imports rclpy only when used."""

    def __init__(self, node_name: str | None = None):
        self.node_name = node_name or os.getenv("JENEFAR_ROS2_NODE_NAME", "jenefar_robot")

    def list_topics(self) -> list[dict[str, object]]:
        try:
            import rclpy
        except Exception as exc:
            raise RuntimeError("ROS2 integration requires a ROS2 installation with rclpy.") from exc

        rclpy.init(args=None)
        node = rclpy.create_node(self.node_name)
        try:
            return [
                {"name": name, "types": list(types)}
                for name, types in node.get_topic_names_and_types()
            ]
        finally:
            node.destroy_node()
            rclpy.shutdown()

    def publish(
        self,
        topic: str,
        message_type: str,
        payload: str,
    ) -> dict[str, Any]:
        topic = topic.strip()
        message_type = message_type.strip()
        if not topic or not message_type or len(payload) > 4000:
            raise ValueError("ROS2 topic, type and payload must be valid and bounded.")

        try:
            import importlib
            import rclpy
        except Exception as exc:
            raise RuntimeError("ROS2 integration requires a ROS2 installation with rclpy.") from exc

        module_name, class_name = message_type.rsplit(".", 1)
        message_class = getattr(importlib.import_module(module_name), class_name)

        rclpy.init(args=None)
        node = rclpy.create_node(self.node_name)
        try:
            publisher = node.create_publisher(message_class, topic, 10)
            message = message_class()
            if hasattr(message, "data"):
                message.data = payload
            else:
                raise ValueError("Configured ROS2 message class must expose a 'data' field.")
            publisher.publish(message)
            return {
                "node": self.node_name,
                "topic": topic,
                "message_type": message_type,
                "published": True,
            }
        finally:
            node.destroy_node()
            rclpy.shutdown()
