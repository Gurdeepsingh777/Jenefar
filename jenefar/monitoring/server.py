from __future__ import annotations

import asyncio
import json

import websockets

from .system_monitor import get_system_stats


CLIENTS=set()


async def send_stats():

    while True:

        data=get_system_stats()

        payload=json.dumps(data)


        dead=[]

        for client in CLIENTS:

            try:
                await client.send(payload)

            except:
                dead.append(client)


        for client in dead:
            CLIENTS.remove(client)


        await asyncio.sleep(1)



async def handler(websocket):

    CLIENTS.add(websocket)

    try:

        while True:

            await websocket.wait()

    finally:

        CLIENTS.remove(websocket)



async def start_monitor_server():

    server=await websockets.serve(
        handler,
        "127.0.0.1",
        8765
    )


    print(
        "[JENEFAR] Monitoring websocket :8765"
    )


    await asyncio.gather(
        server.wait_closed(),
        send_stats()
    )
