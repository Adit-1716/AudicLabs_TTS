from fastapi import APIRouter

from app.routers import core, media, ops, samples, transcripts, tts

api = APIRouter()
api.include_router(core.router)
api.include_router(media.router)
api.include_router(transcripts.router)
api.include_router(ops.router)
api.include_router(samples.router)
api.include_router(tts.router)
