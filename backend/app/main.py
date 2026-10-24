from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.routers import api
from app.seed import seed
from app.services.storage import ensure_bucket


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    try:
        ensure_bucket()
    except Exception as exc:
        print("storage init skipped:", exc)
    yield


app = FastAPI(title="Transcribe Hub API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api, prefix="/api")


@app.get("/health")
def health():
    return {"ok": True, "service": "transcribe-hub"}


class Hub:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}

    async def join(self, room: str, ws: WebSocket):
        await ws.accept()
        self.rooms.setdefault(room, []).append(ws)

    def leave(self, room: str, ws: WebSocket):
        self.rooms.get(room, []).remove(ws) if ws in self.rooms.get(room, []) else None

    async def broadcast(self, room: str, payload: dict, skip: WebSocket | None = None):
        for peer in list(self.rooms.get(room, [])):
            if peer is skip:
                continue
            try:
                await peer.send_json(payload)
            except Exception:
                self.leave(room, peer)


hub = Hub()


@app.websocket("/ws/{room}")
async def ws_room(websocket: WebSocket, room: str):
    await hub.join(room, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await hub.broadcast(room, {"from": "peer", **data}, skip=websocket)
    except WebSocketDisconnect:
        hub.leave(room, websocket)
