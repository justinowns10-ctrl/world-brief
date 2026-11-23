"""Read-only HTTP API for the Android app. Single user, one bearer token."""
from __future__ import annotations

import hmac
import re
import threading

from fastapi import Depends, FastAPI, Header, HTTPException

from . import PIPELINE_VERSION, db

_ID = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def create_app(db_path: str, token: str) -> FastAPI:
    if not token or len(token) < 16:
        raise ValueError("API token must be at least 16 characters")
    app = FastAPI(title="World Brief", docs_url=None, redoc_url=None, openapi_url=None)
    conn = db.connect(db_path)
    lock = threading.Lock()
    expected = f"Bearer {token}".encode()

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not hmac.compare_digest(authorization.encode(), expected):
            raise HTTPException(status_code=401, detail="Invalid or missing token",
                                headers={"WWW-Authenticate": "Bearer"})

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "service": "worldbrief", "version": PIPELINE_VERSION, "schemaVersion": 1}

    @app.get("/v1/status", dependencies=[Depends(require_token)])
    def status():
        """State of the latest run: pending, complete, partial or failed."""
        with lock:
            return db.latest_run_status(conn)

    @app.get("/v1/briefings", dependencies=[Depends(require_token)])
    def briefings():
        with lock:
            return {"briefings": db.list_briefings(conn)}

    @app.get("/v1/briefings/latest", dependencies=[Depends(require_token)])
    def latest():
        with lock:
            listed = db.list_briefings(conn)
            briefing = db.get_briefing(conn, listed[0]["id"]) if listed else None
        if briefing is None:
            raise HTTPException(status_code=404, detail="No briefing has been published yet")
        return briefing

    @app.get("/v1/briefings/{briefing_id}", dependencies=[Depends(require_token)])
    def one(briefing_id: str):
        if not _ID.match(briefing_id):
            raise HTTPException(status_code=404, detail="Unknown briefing")
        with lock:
            briefing = db.get_briefing(conn, briefing_id)
        if briefing is None:
            raise HTTPException(status_code=404, detail="Unknown briefing")
        return briefing

    return app
