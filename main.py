#!/usr/bin/env python
"""CLIConductor — entry point."""

import os
from datetime import datetime

from src.server import app

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("CLICONDUCTOR_HOST", "127.0.0.1")
    port = int(os.environ.get("CLICONDUCTOR_PORT", "8767"))

    tm = datetime.now().strftime("%H:%M:%S")
    print(f"[{tm}] CLIConductor starting on {host}:{port}")

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    server.run()
