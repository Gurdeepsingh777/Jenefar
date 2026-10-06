from __future__ import annotations
import os
import signal
import threading

from jenefar.avatar.controller import AvatarController
from jenefar.avatar.server import AvatarServer
from jenefar.core.orchestrator import JenefarOrchestrator
from jenefar.production.readiness import check

def main() -> int:
    readiness = check()
    if not readiness["ready"]:
        print({"ready": False, "failures": readiness["failures"]})
        return 2
    avatar = AvatarController()
    orchestrator = JenefarOrchestrator(avatar=avatar)
    server = AvatarServer(
        avatar,
        host=os.getenv("JENEFAR_HOST", "127.0.0.1"),
        port=int(os.getenv("JENEFAR_AVATAR_PORT", "8787")),
        vrm_path=None,
        tool_broker=orchestrator.tool_broker,
        runtime_status=orchestrator.runtime_status,
        cancel_active_task=orchestrator.cancel_active_task,
        runtime_tasks=orchestrator.runtime_tasks,
    )
    server.start()
    print({"ready": True, "url": server.url})
    stop = threading.Event()
    def shutdown(_sig, _frame):
        stop.set()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        stop.wait()
    finally:
        server.stop()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
