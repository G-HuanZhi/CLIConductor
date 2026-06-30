#!/usr/bin/env python
"""CLIConductor — entry point."""

from datetime import datetime

from src.server import app

if __name__ == "__main__":
    import uvicorn

    tm = datetime.now().strftime("%H:%M:%S")
    print(f"[{tm}] CLIConductor starting on 127.0.0.1:8767")

    config = uvicorn.Config(app, host="127.0.0.1", port=8767, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    server.run()
