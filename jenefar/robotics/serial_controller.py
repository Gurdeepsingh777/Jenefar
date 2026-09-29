from __future__ import annotations

import os
import re


SAFE_COMMANDS = {"status", "stop", "forward", "backward", "left", "right", "home"}


class SerialRobotController:
    """Explicit serial bridge for basic, bounded robot commands."""

    def __init__(self, port: str | None = None, baudrate: int | None = None):
        self.port = port or os.getenv("JENEFAR_ROBOT_SERIAL_PORT", "").strip()
        self.baudrate = int(baudrate or os.getenv("JENEFAR_ROBOT_BAUDRATE", "115200"))

    def list_ports(self) -> list[dict[str, str]]:
        try:
            from serial.tools import list_ports
        except Exception as exc:
            raise RuntimeError("Robotics serial integration requires optional 'pyserial'.") from exc
        return [
            {"device": item.device, "description": item.description or ""}
            for item in list_ports.comports()
        ]

    def command(self, command: str, argument: str = "") -> dict[str, str]:
        command = command.strip().lower()
        argument = argument.strip()
        if command not in SAFE_COMMANDS and command != "servo":
            raise ValueError(f"Unsupported robot command: {command}")
        if command == "servo" and not re.fullmatch(r"(?:0|[1-9]\d?|1[0-7]\d|180)", argument):
            raise ValueError("Servo angle must be an integer from 0 to 180.")
        if not self.port:
            raise ValueError("JENEFAR_ROBOT_SERIAL_PORT is not configured.")

        try:
            import serial
        except Exception as exc:
            raise RuntimeError("Robotics serial integration requires optional 'pyserial'.") from exc

        wire = command if not argument else f"{command}:{argument}"
        with serial.Serial(self.port, self.baudrate, timeout=2) as connection:
            connection.write((wire + "\n").encode("utf-8"))
            response = connection.readline().decode("utf-8", errors="replace").strip()

        return {
            "port": self.port,
            "baudrate": str(self.baudrate),
            "command": wire,
            "response": response,
        }
