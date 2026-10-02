from __future__ import annotations

import asyncio
import json
import time

from websockets.asyncio.server import serve

from .system_monitor import get_system_stats


HOST = "127.0.0.1"
PORT = 8765
UPDATE_INTERVAL = 1.0

CLIENTS: set = set()


async def send_stats() -> None:
    """Collect and broadcast real system telemetry once per second."""
    while True:
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
        await asyncio.sleep(max(0.0, UPDATE_INTERVAL - elapsed))


async def handler(websocket) -> None:
    CLIENTS.add(websocket)
    print(f"[JENEFAR] Monitoring client connected ({len(CLIENTS)})")

    try:
        await websocket.wait_closed()
    finally:
        CLIENTS.discard(websocket)
        print(f"[JENEFAR] Monitoring client disconnected ({len(CLIENTS)})")


async def main() -> None:
    async with serve(handler, HOST, PORT) as server:
        print(f"[JENEFAR] Monitoring websocket running ws://{HOST}:{PORT}")
        await send_stats()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[JENEFAR] Monitoring server stopped")
