from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass

from websockets.asyncio.server import serve

from .system_monitor import get_system_stats


HOST = "127.0.0.1"
PORT = 8765
UPDATE_INTERVAL = 1.0

CLIENTS: set = set()


async def send_stats(stop_event: asyncio.Event | None = None) -> None:
    """Collect and broadcast real system telemetry once per second."""
    while stop_event is None or not stop_event.is_set():
        started = time.monotonic()

        try:
            data = get_system_stats()
            payload = json.dumps(data)

            disconnected = []

            for client in tuple(CLIENTS):
                try:
                    await client.send(payload)
                except Exception:
                    disconnected.append(client)

            for client in disconnected:
                CLIENTS.discard(client)

        except Exception as exc:
            print(f"[JENEFAR] Monitoring error: {exc}")

        elapsed = time.monotonic() - started
        remaining = max(0.0, UPDATE_INTERVAL - elapsed)

        if stop_event is None:
            await asyncio.sleep(remaining)
        else:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                pass


async def handler(websocket) -> None:
    CLIENTS.add(websocket)
    print(
        f"[JENEFAR] Monitoring client connected "
        f"({len(CLIENTS)})"
    )

    try:
        await websocket.wait_closed()
    finally:
        CLIENTS.discard(websocket)
        print(
            f"[JENEFAR] Monitoring client disconnected "
            f"({len(CLIENTS)})"
        )


@dataclass
class MonitoringServer:
    """Managed background WebSocket telemetry service."""

    host: str = HOST
    port: int = PORT

    def __post_init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._server = None
        self._ready = threading.Event()
        self._error: BaseException | None = None

    @property
    def running(self) -> bool:
        return bool(
            self._thread
            and self._thread.is_alive()
            and self._server is not None
        )

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def start(self) -> None:
        if self.running:
            return

        self._ready.clear()
        self._error = None

        self._thread = threading.Thread(
            target=self._run,
            name="jenefar-monitoring-server",
            daemon=True,
        )
        self._thread.start()

        self._ready.wait(timeout=5.0)

        if self._error is not None:
            error = self._error
            self._thread = None
            raise RuntimeError(
                f"Monitoring server failed to start: "
                f"{type(error).__name__}: {error}"
            ) from error

        if not self.running:
            raise RuntimeError("Monitoring server did not become ready")

        print(
            f"[JENEFAR] Monitoring WebSocket: {self.url}"
        )

    def stop(self) -> None:
        loop = self._loop
        stop_event = self._stop_event

        if loop is None or stop_event is None:
            return

        try:
            loop.call_soon_threadsafe(stop_event.set)
        except RuntimeError:
            pass

        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3.0)

        self._thread = None
        self._loop = None
        self._stop_event = None
        self._server = None

        print("[JENEFAR] Monitoring server stopped")

    def _run(self) -> None:
        try:
            asyncio.run(self._async_main())
        except BaseException as exc:
            self._error = exc
            self._ready.set()

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        async with serve(
            handler,
            self.host,
            self.port,
        ) as server:
            self._server = server
            self._ready.set()

            await send_stats(self._stop_event)

        self._server = None


def start_monitoring_server(
    host: str = HOST,
    port: int = PORT,
) -> MonitoringServer:
    """Start and return a managed monitoring server."""
    server = MonitoringServer(host=host, port=port)
    server.start()
    return server


async def main() -> None:
    """Standalone monitoring-server entrypoint."""
    async with serve(handler, HOST, PORT):
        print(
            f"[JENEFAR] Monitoring websocket running "
            f"ws://{HOST}:{PORT}"
        )
        await send_stats()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[JENEFAR] Monitoring server stopped")
