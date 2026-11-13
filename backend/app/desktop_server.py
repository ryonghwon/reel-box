"""Loopback-only server for the bundled desktop renderer and local queue."""

import json
import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .egress import Proxy, Server


def main():
    if os.getenv("REELBOX_DESKTOP") != "1":
        raise RuntimeError("Desktop mode required")
    proxy = Server(("127.0.0.1", 0), Proxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    os.environ["EGRESS_PROXY"] = f"http://127.0.0.1:{proxy.server_address[1]}"
    from .main import app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"

    @app.middleware("http")
    async def desktop_boundary(request, call_next):
        if request.headers.get("host") != f"127.0.0.1:{port}":
            return JSONResponse({"detail": "Local app only"}, status_code=403)
        if (
            request.headers.get("origin") not in (None, origin)
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            return JSONResponse({"detail": "Origin rejected"}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount(
        "/",
        StaticFiles(directory=Path(os.environ["REELBOX_WEB_DIR"]), html=True),
        name="desktop-ui",
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", access_log=False
        )
    )

    def watch_parent():
        sys.stdin.buffer.read()
        server.should_exit = True

    threading.Thread(target=watch_parent, daemon=True).start()
    print("REELBOX_READY " + json.dumps({"port": port}), flush=True)
    try:
        server.run(sockets=[sock])
    finally:
        proxy.shutdown()
        proxy.server_close()
        sock.close()


if __name__ == "__main__":
    main()
