from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any


class ReaMCPClient:
    """Optional stdio MCP client for the official REA server.

    Uses the MCP SDK's stdio transport; tools and argument contracts are
    discovered from REA at runtime. It never constructs shell command strings.
    """

    def __init__(self) -> None:
        self.enabled = os.getenv("JENEFAR_REA_ENABLED", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.command = os.getenv("JENEFAR_REA_COMMAND", "npx").strip() or "npx"
        raw_args = os.getenv(
            "JENEFAR_REA_ARGS",
            "--yes,--package=rea-agents@6.5.0,--,rea,mcp",
        )
        self.args = [item.strip() for item in raw_args.split(",") if item.strip()]
        # Migrate existing .env files from the ambiguous npx package/bin shorthand
        # to npm's explicit package-runner form. This is intentionally limited to
        # the known REA command shape and never invokes a shell.
        if (
            os.path.basename(self.command) in {"npx", "npx.cmd"}
            and len(self.args) == 3
            and self.args[0] in {"-y", "--yes"}
            and self.args[1].startswith("rea-agents@")
            and self.args[2] == "mcp"
        ):
            package = self.args[1]
            self.args = ["--yes", f"--package={package}", "--", "rea", "mcp"]
        self.timeout = max(
            5.0,
            min(600.0, float(os.getenv("JENEFAR_REA_TIMEOUT_SECONDS", "120"))),
        )
        self.max_result_chars = max(
            1000,
            min(100000, int(os.getenv("JENEFAR_REA_MAX_RESULT_CHARS", "20000"))),
        )
        self._lock = threading.RLock()
        self._next_id = 1
        self._process: subprocess.Popen[bytes] | None = None
        self._pending_output = bytearray()
        self._tools: dict[str, dict[str, Any]] = {}
        self._last_error = ""
        self._stderr_tail = bytearray()
        self._stderr_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None

    @staticmethod
    def _resolve_executable(command: str) -> str | None:
        return command if os.path.isabs(command) else shutil.which(command)

    def _node_diagnostic(self) -> str:
        node = self._resolve_executable("node")
        if not node:
            return "Node.js was not found on Jenefar's PATH."
        try:
            result = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=5, check=False
            )
            raw = result.stdout.strip().lstrip("v")
            parts = raw.split(".")
            major, minor = int(parts[0]), int(parts[1])
            supported = (
                major >= 26
                or (major == 24 and minor >= 11)
                or (major == 22 and minor >= 19)
            )
            if result.returncode != 0 or not supported:
                return (
                    "REA requires Node.js 22.19+, 24.11+, or 26+; "
                    f"detected {raw or 'unknown'}."
                )
        except Exception as exc:
            return f"Could not check Node.js: {type(exc).__name__}: {exc}"
        return ""

    def _configuration_diagnostic(self) -> str:
        if not self.enabled:
            return "REA bridge is disabled. Set JENEFAR_REA_ENABLED=true in .env."
        if not self.command:
            return "JENEFAR_REA_COMMAND is empty."
        command_path = self._resolve_executable(self.command)
        if not command_path or not os.path.isfile(command_path) or not os.access(command_path, os.X_OK):
            return (
                f"REA command '{self.command}' was not found or is not executable. "
                "Set JENEFAR_REA_COMMAND to the absolute path to npx."
            )
        return self._node_diagnostic()

    def _drain_stderr(self, stream) -> None:
        """Continuously drain child stderr so a noisy npm wrapper cannot block MCP."""
        try:
            while True:
                chunk = stream.read(1024)
                if not chunk:
                    return
                with self._stderr_lock:
                    self._stderr_tail.extend(chunk)
                    if len(self._stderr_tail) > 12000:
                        del self._stderr_tail[:-12000]
        except (OSError, ValueError):
            return

    def _stderr_diagnostic(self) -> str:
        with self._stderr_lock:
            raw = bytes(self._stderr_tail[-4000:])
        return raw.decode("utf-8", errors="replace").strip()

    def status(self) -> dict[str, Any]:
        with self._lock:
            configuration_error = self._configuration_diagnostic()
            connected = bool(self._process and self._process.poll() is None)
            return {
                "enabled": self.enabled,
                "command": self.command,
                "args": self.args,
                "connected": connected,
                "advertised_tools": len(self._tools),
                "ready": not bool(configuration_error) and not bool(self._last_error),
                "last_error": self._last_error or configuration_error,
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
                raise ValueError(
                    f"Unknown REA tool '{name}'. Call rea_list_tools to discover supported names."
                )
            if not isinstance(arguments, dict):
                raise ValueError("REA tool arguments must be a JSON object.")
            self._validate_arguments(spec.get("inputSchema", {}), arguments)
            result = self._request("tools/call", {"name": name, "arguments": arguments})
            if result.get("isError"):
                raise RuntimeError(
                    self._content_text(result.get("content", []))[:2000]
                    or f"REA tool '{name}' returned an error."
                )
            text_value = self._content_text(result.get("content", []))
            if len(text_value) > self.max_result_chars:
                text_value = (
                    text_value[:self.max_result_chars]
                    + "\n[Truncated by Jenefar. Request a focused REA result or page.]"
                )
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
            valid_types = expected if isinstance(expected, list) else ([expected] if isinstance(expected, str) else [])
            checks = {
                "string": lambda v: isinstance(v, str),
                "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
                "boolean": lambda v: isinstance(v, bool),
                "object": lambda v: isinstance(v, dict),
                "array": lambda v: isinstance(v, list),
                "null": lambda v: v is None,
            }
            valid_expected = [typ for typ in valid_types if typ in checks]
            if valid_expected and not any(checks[typ](value) for typ in valid_expected):
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
        # REA 6.5.0 launches over MCP stdio. Resolve npx and its Node.js runtime
        # explicitly so the bridge is not dependent on the desktop shell PATH.
        problem = self._configuration_diagnostic()
        if problem:
            raise RuntimeError(problem)
        if self._process is not None and self._process.poll() is None:
            return
        self._stop_process()
        self._last_error = ""
        command_path = self._resolve_executable(self.command)
        if not command_path:
            raise RuntimeError(f"Could not resolve REA command: {self.command}")
        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        env["CI"] = "1"
        env["npm_config_yes"] = "true"
        # npm/npx diagnostic chatter belongs on stderr, which is drained on a
        # background thread; stdout is reserved for MCP JSON-RPC messages.
        with self._stderr_lock:
            self._stderr_tail.clear()
        try:
            self._process = subprocess.Popen(
                [command_path, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=env,
            )
            if self._process.stderr is not None:
                self._stderr_thread = threading.Thread(
                    target=self._drain_stderr,
                    args=(self._process.stderr,),
                    name="jenefar-rea-stderr",
                    daemon=True,
                )
                self._stderr_thread.start()
            init = self._request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "jenefar-rea-bridge", "version": "1.0.0"},
                },
            )
            if not isinstance(init, dict) or not isinstance(init.get("serverInfo", {}), dict):
                raise RuntimeError("REA returned an invalid MCP initialize result.")
            self._notify("notifications/initialized", {})
            self._tools = self._load_tool_catalog()
            if not self._tools:
                raise RuntimeError("REA connected but advertised no MCP tools.")
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._stop_process()
            diagnostic = self._stderr_diagnostic()
            if diagnostic:
                self._last_error += f" | REA stderr: {diagnostic}"
            raise RuntimeError(f"Could not connect to REA MCP server: {self._last_error}") from exc

    def _read_message(self, deadline: float) -> dict[str, Any]:
        """Read one newline-delimited JSON-RPC message from MCP stdio."""
        import select

        process = self._process
        if process is None or process.stdout is None:
            raise RuntimeError("REA MCP process is not running.")
        fd = process.stdout.fileno()
        data = bytearray(self._pending_output)
        self._pending_output.clear()

        while time.monotonic() < deadline:
            newline = data.find(b"\n")
            if newline >= 0:
                line = bytes(data[:newline]).strip()
                del data[:newline + 1]
                if not line:
                    continue
                try:
                    message = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("REA MCP returned invalid newline-delimited JSON-RPC.") from exc
                if not isinstance(message, dict):
                    raise RuntimeError("REA MCP returned a non-object JSON-RPC message.")
                # Preserve additional JSON-RPC lines delivered by the same OS read.
                self._pending_output.extend(data)
                return message

            remaining = max(0.05, deadline - time.monotonic())
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.25))
            if not ready:
                if process.poll() is not None:
                    raise RuntimeError("REA MCP process exited while waiting for a response.")
                continue
            chunk = os.read(fd, 4096)
            if not chunk:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"REA MCP closed stdout unexpectedly (process exit code {process.poll()})."
                    )
                continue
            data.extend(chunk)
            if len(data) > 32 * 1024 * 1024 and b"\n" not in data:
                raise RuntimeError("REA MCP output line exceeded the 32 MiB safety limit.")
        raise TimeoutError("Timed out reading REA MCP response.")

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            raise RuntimeError("REA MCP process is not running.")
        request_id = self._next_id
        self._next_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            os.write(process.stdin.fileno(), payload + b"\\n")
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError("Could not write an MCP request to REA.") from exc
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = self._read_message(deadline)
            if message.get("id") != request_id:
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
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            os.write(process.stdin.fileno(), payload + b"\\n")
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError("Could not write an MCP notification to REA.") from exc

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

    def _stop_process(self) -> None:
        process, self._process = self._process, None
        self._tools = {}
        if process is not None:
            try:
                if process.stdin:
                    process.stdin.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except Exception:
                    pass

            thread = self._stderr_thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=0.4)
            for stream in (process.stdout, process.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
        self._stderr_thread = None

    def close(self) -> None:
        with self._lock:
            self._stop_process()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
