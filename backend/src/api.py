
"""TaskButler - FastAPI Token Server

Provides:
  GET /health -> {"status": "ok"}
  GET /token?room={room_name}&identity={identity} -> LiveKit JWT access token
  POST /speak {text, room} -> ask the agent in {room} to speak {text}
"""

import json
import logging
import os

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from livekit import api as livekit_api

logger = logging.getLogger(__name__)

app = FastAPI(title="TaskButler API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/token")
async def get_token(
    room: str = Query(..., description="Room name to join"),
    identity: str = Query(..., description="Participant identity"),
):
    """Generate a LiveKit access token for the frontend."""
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500,
            detail="LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set"
        )

    token = (
        livekit_api.AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
    )

    jwt_token = token.to_jwt()
    return {
        "token": jwt_token,
        "url": os.getenv("LIVEKIT_URL", ""),
    }


@app.post("/speak")
async def speak_text(request: Request):
    """Tell the LiveKit agent in a given room to speak the supplied text via TTS."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json body"}, status_code=400)

    text = (body.get("text") or "").strip()
    room_name = (body.get("room") or "").strip()

    if not text or not room_name:
        return JSONResponse(
            {"error": "text and room required"}, status_code=400
        )

    try:
        lk = livekit_api.LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        payload = json.dumps({"type": "speak_request", "text": text}).encode("utf-8")
        await lk.room.send_data(
            livekit_api.SendDataRequest(
                room=room_name,
                data=payload,
                kind=livekit_api.DataPacket.Kind.RELIABLE
                if hasattr(livekit_api, "DataPacket")
                else 0,
            )
        )
        return JSONResponse({"status": "sent", "text": text})
    except Exception as e:
        logger.warning("speak forwarding failed: %s", e)
        # Best-effort: never 500 the client; the frontend treats this as fire-and-forget.
        return JSONResponse({"status": "ok", "note": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
