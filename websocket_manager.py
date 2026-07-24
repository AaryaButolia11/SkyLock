from fastapi import WebSocket
from typing import Dict, List

class ConnectionManager:
    """
    Tracks which WebSocket connections are currently watching which flight's
    seat map, so we can broadcast seat events only to relevant clients.
    """
    def __init__(self):
        self.active: Dict[int, List[WebSocket]] = {}

    async def connect(self, flight_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(flight_id, []).append(websocket)

    def disconnect(self, flight_id: int, websocket: WebSocket):
        if flight_id in self.active and websocket in self.active[flight_id]:
            self.active[flight_id].remove(websocket)
            if not self.active[flight_id]:
                del self.active[flight_id]

    async def broadcast(self, flight_id: int, message: dict):
        for ws in list(self.active.get(flight_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(flight_id, ws)  # dead connection, clean it up

manager = ConnectionManager()