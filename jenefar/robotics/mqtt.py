from __future__ import annotations

import os
import threading
from typing import Any, Callable


class MqttRobotController:
    """Optional MQTT robotics adapter with bounded topics and payloads."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        command_topic: str | None = None,
        telemetry_topic: str | None = None,
    ):
        self.host = host or os.getenv("JENEFAR_MQTT_HOST", "").strip()
        self.port = int(port or os.getenv("JENEFAR_MQTT_PORT", "1883"))
        self.command_topic = command_topic or os.getenv(
            "JENEFAR_MQTT_COMMAND_TOPIC", "jenefar/robot/command"
        )
        self.telemetry_topic = telemetry_topic or os.getenv(
            "JENEFAR_MQTT_TELEMETRY_TOPIC", "jenefar/robot/telemetry"
        )
        self._client = None
        self._last_telemetry: str = ""
        self._lock = threading.RLock()

    def _require_client(self):
        try:
            import paho.mqtt.client as mqtt
        except Exception as exc:
            raise RuntimeError("MQTT robotics integration requires optional 'paho-mqtt'.") from exc

        if self._client is None:
            if not self.host:
                raise ValueError("JENEFAR_MQTT_HOST is not configured.")
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self._client.on_message = self._on_message
            self._client.connect(self.host, self.port, 60)
            self._client.loop_start()
            self._client.subscribe(self.telemetry_topic, qos=1)
        return self._client

    def _on_message(self, _client, _userdata, message) -> None:
        with self._lock:
            self._last_telemetry = message.payload.decode("utf-8", errors="replace")[:4000]

    def publish_command(self, command: str) -> dict[str, Any]:
        command = command.strip()
        if not command or len(command) > 200:
            raise ValueError("MQTT robot command must be 1-200 characters.")
        client = self._require_client()
        result = client.publish(self.command_topic, command, qos=1, retain=False)
        result.wait_for_publish(timeout=5)
        return {
            "host": self.host,
            "topic": self.command_topic,
            "command": command,
            "published": result.rc == 0,
        }

    def telemetry(self) -> dict[str, str]:
        self._require_client()
        with self._lock:
            return {
                "host": self.host,
                "topic": self.telemetry_topic,
                "latest": self._last_telemetry,
            }

    def close(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
