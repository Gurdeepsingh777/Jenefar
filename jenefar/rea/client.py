from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlsplit


class ReaMCPClient:
    """Small stdio MCP client for the official REA server.

    Only caller-configured commands are spawned. MCP tools are discovered from
    the server and validated against the advertised JSON schema before call.
    """

    def __init__(self) -> None:
        self.enabled = os.getenv("JENEFAR_REA_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.command = os.getenv("JENEFAR_REA_COMMAND", "npx").strip() or "npx"
        raw_args = os.getenv("JENEFAR_REA_ARGS", "-y,rea-agents@6.5.0,mcp")
        self.args = [item.strip() for item in raw_args.split(",") if item.strip()]
        self.env = dict(os.environ)
        self.cwd = os.getcwd()
        self.timeout = max(5.0, min(600.0, float(os.getenv("JENEFAR_REA_TIMEOUT_SECONDS", "120"))))
        self.max_result_chars = max(1000, min(100000, int(os.getenv("JENEFAR_REA_MAX_RESULT_CHARS", "20000"))))
        self._lock = threading.RLock()
        self._next_id = 1
        self._process: subprocess.Popen[str] | None = None
        self._tools: dict[str, dict[str, Any]] = {}
        self._last_error = ""

    @staticmethod
    def _node_runtime_ready(command: str) -> tuple[bool, str]:
        if os.path.isabs(command):
            if not os.path.isfile(command) or not os.access(command, os.X_OK):
                return False, f"Configured REA command is not an executable file: {command}"
        elif shutil.which(command) is None:
            return False, f"REA command '{command}' was not found on PATH. Install Node.js/npm or set JENEFAR_REA_COMMAND to an absolute npx path."
        node = shutil.which("node")
        if node is None:
            return False, "Node.js is required by REA. Install a supported Node.js release (22.19+, 24.11+, or 26+) separately."
        try:
            result = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=5, check=False
            )
            version = result.stdout.strip().lstrip("v").split(".")
            major, minor = int(version[0]), int(version[1])
            supported = major >= 26 or (major == 24 and minor >= 11) or (major == 22 and minor >= 19)
            if not supported:
                return False, f"REA needs Node.js 22.19+, 24.11+, or 26+; detected {result.stdout.strip() or 'unknown'}."
        except Exception as exc:
            return False, f"Could not check Node.js version: {type(exc).__name__}: {exc}"
        return True, ""

    def status(self) -> dict[str, Any]:
        with self._lock:
            ready, reason = self._node_runtime_ready(self.command) if self.enabled else (False, "REA bridge is disabled. Set JENEFAR_REA_ENABLED=true to enable it.")
            return {
                "enabled": self.enabled,
                "command": self.command,
                "args": self.args,
                "node_ready": ready,
                "connected": bool(self._process and self._process.poll() is None),
                "advertised_tools": len(self._tools),
                "last_error": self._last_error or reason,
            }

    def list_tools(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            tools = [
                {
                    "name": name,
                    "description": str(spec.get("description", ""))[:800],
                    "inputSchema": spec.get("inputSchema", {"type": "object", "properties": {}}),
                }
                for name, spec in sorted(self._tools.items())
            ]
            return {"server": "rea", "count": len(tools), "tools": tools}

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            spec = self._tools.get(str(name))
            if spec is None:
                raise ValueError(f"Unknown REA tool '{name}'. Call rea_list_tools to discover supported names.")
            if not isinstance(arguments, dict):
                raise ValueError("REA tool arguments must be a JSON object.")
            self._validate_arguments(spec.get("inputSchema", {}), arguments)
            result = self._request("tools/call", {"name": name, "arguments": arguments})
            if result.get("isError"):
                raise RuntimeError(self._content_text(result.get("content", []))[:2000] or f"REA tool '{name}' returned an error.")
            text_value = self._content_text(result.get("content", []))
            if len(text_value) > self.max_result_chars:
                text_value = text_value[:self.max_result_chars] + "\n[Truncated by Jenefar; query REA with a more specific request for full details.]"
            return {
                "server": "rea",
                "tool": name,
                "structuredContent": result.get("structuredContent"),
                "content": text_value,
            }

    @staticmethod
    def _content_text(content: Any) -> str:
        if not isinstance(content, list):
            return str(content or "")
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("text") is not None:
                    parts.append(str(block["text"]))
                elif block.get("type") == "image":
                    parts.append("[REA returned image content]")
                else:
                    parts.append(json.dumps(block, ensure_ascii=False, default=str))
            else:
                parts.append(str(block))
        return "\n".join(parts)

    @classmethod
    def _validate_arguments(cls, schema: dict[str, Any], arguments: dict[str, Any]) -> None:
        if not schema:
            return
        if schema.get("type") not in (None, "object"):
            raise ValueError("REA tool schema is not an object schema.")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ValueError("REA advertised a malformed input schema.")
        missing = [key for key in required if key not in arguments]
        if missing:
            raise ValueError("Missing required REA argument(s): " + ", ".join(map(str, missing)))
        if schema.get("additionalProperties") is False:
            extra = [key for key in arguments if key not in properties]
            if extra:
                raise ValueError("Unexpected REA argument(s): " + ", ".join(extra))
        for key, value in arguments.items():
            prop = properties.get(key)
            if not isinstance(prop, dict):
                continue
            expected = prop.get("type")
            if isinstance(expected, list):
                valid_types = expected
            elif isinstance(expected, str):
                valid_types = [expected]
            else:
                valid_types = []
            ok = True
            if "string" in valid_types:
                ok = isinstance(value, str)
            elif "integer" in valid_types:
                ok = isinstance(value, int) and not isinstance(value, bool)
            elif "number" in valid_types:
                ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            elif "boolean" in valid_types:
                ok = isinstance(value, bool)
            elif "object" in valid_types:
                ok = isinstance(value, dict)
            elif "array" in valid_types:
                ok = isinstance(value, list)
            elif "null" in valid_types:
                ok = value is None
            if valid_types and not ok:
                raise ValueError(f"REA argument '{key}' must match schema type {expected}.")
            if isinstance(value, str):
                if len(value) < int(prop.get("minLength", 0)):
                    raise ValueError(f"REA argument '{key}' is shorter than its schema minimum.")
                if "maxLength" in prop and len(value) > int(prop["maxLength"]):
                    raise ValueError(f"REA argument '{key}' exceeds the schema maximum length.")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if "minimum" in prop and value < prop["minimum"]:
                    raise ValueError(f"REA argument '{key}' is below its schema minimum.")
                if "maximum" in prop and value > prop["maximum"]:
                    raise ValueError(f"REA argument '{key}' exceeds its schema maximum.")

    def _ensure_connected(self) -> None:
        if not self.enabled:
            raise RuntimeError("REA bridge is disabled. Set JENEFAR_REA_ENABLED=true in .env and restart Jenefar.")
        ready, reason = self._node_runtime_ready(self.command)
        if not ready:
            raise RuntimeError(reason)
        if self._process is not None and self._process.poll() is None:
            return
        self._stop_process()
        self._last_error = ""
        command_path = shutil.which(self.command) if not os.path.isabs(self.command) else self.command
        if not command_path:
            raise RuntimeError(f"Could not resolve REA command: {self.command}")
        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        # MCP stdio uses Content-Length framed JSON-RPC messages in the current
        # protocol, not newline-delimited JSON. Use the SDK framing for requests.
        try:
            self._process = subprocess.Popen(
                [command_path, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            init = self._request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "jenefar-rea-bridge", "version": "1.0.0"},
                },
            )
            if not isinstance(init, dict):
                raise RuntimeError("REA returned an invalid MCP initialize result.")
            self._notify("notifications/initialized", {})
            self._tools = self._load_tool_catalog()
            if not self._tools:
                raise RuntimeError("REA connected but advertised no MCP tools.")
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._stop_process()
            raise RuntimeError(f"Could not connect to REA MCP server: {self._last_error}") from exc

    def _load_tool_catalog(self) -> dict[str, dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        if not isinstance(tools, list):
            raise RuntimeError("REA returned a malformed MCP tool catalog.")
        catalog: dict[str, dict[str, Any]] = {}
        for spec in tools:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name", "")).strip()
            schema = spec.get("inputSchema", {"type": "object", "properties": {}})
            if name and isinstance(schema, dict):
                catalog[name] = spec
        return catalog

    def _read_exact(self, size: int, deadline: float) -> bytes:
        import select

        process = self._process
        if process is None or process.stdout is None:
            raise RuntimeError("REA MCP process is not running.")
        result = bytearray()
        fd = process.stdout.fileno()
        while len(result) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out reading REA MCP response.")
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.25))
            if not ready:
                if process.poll() is not None:
                    raise RuntimeError("REA MCP process exited while sending a response.")
                continue
            chunk = os.read(fd, size - len(result))
            if not chunk:
                raise RuntimeError("REA MCP closed stdout unexpectedly.")
            result.extend(chunk)
        return bytes(result)

    def _read_message(self, deadline: float) -> dict[str, Any]:
        headers: dict[str, str] = {}
        while True:
            line = bytearray()
            # Read header byte-by-byte to avoid buffered reads hiding body bytes
            # from select on later requests.
            while True:
                chunk = self._read_exact(1, deadline)
                line.extend(chunk)
                if line.endswith(b"\r\n"):
                    break
                if len(line) > 8192:
                    raise RuntimeError("REA MCP header line is too long.")
            if line == b"\r\n":
                break
            header = bytes(line[:-2]).decode("ascii", errors="replace")
            if ":" not in header:
                raise RuntimeError("REA MCP returned a malformed header.")
            key, value = header.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise RuntimeError("REA MCP response has no valid Content-Length header.") from exc
        if length < 0 or length > 32 * 1024 * 1024:
            raise RuntimeError("REA MCP response length is outside the permitted bound.")
        body = self._read_exact(length, deadline)
        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("REA MCP returned invalid JSON-RPC data.") from exc
        if not isinstance(message, dict):
            raise RuntimeError("REA MCP returned a non-object JSON-RPC message.")
        return message

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            raise RuntimeError("REA MCP process is not running.")
        request_id = self._next_id
        self._next_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            ensure_ascii=False,
        ).encode("utf-8")
        frame = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
        try:
            process.stdin.buffer.write(frame)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError("Could not write an MCP request to REA.") from exc
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = self._read_message(deadline)
            if message.get("id") != request_id:
                # Ignore notifications / progress messages not tied to this request.
                continue
            if "error" in message:
                error = message["error"]
                raise RuntimeError(
                    f"REA MCP {method} error {error.get('code', '')}: {error.get('message', 'unknown error')}"
                )
            result = message.get("result", {})
            return result if isinstance(result, dict) else {"result": result}
        raise TimeoutError(f"REA MCP {method} timed out after {self.timeout:g}s.")

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("REA MCP process is not running.")
        payload = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params},
            ensure_ascii=False,
        ).encode("utf-8")
        frame = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
        process.stdin.buffer.write(frame)
        process.stdin.flush()

    def _stop_process(self) -> None:
        process, self._process = self._process, None
        self._tools = {}
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            self._stop_process()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
