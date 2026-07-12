#!/usr/bin/env python
"""CLIConductor — entry point."""

import os
from datetime import datetime

from src.server import app

if __name__ == "__main__":
    import uvicorn
    from src.config import load_config

    host = os.environ.get("CLICONDUCTOR_HOST", "127.0.0.1")
    env_port = os.environ.get("CLICONDUCTOR_PORT")
    if env_port is not None:
        port = int(env_port)
    else:
        port = load_config().get("port", 8767)

    tm = datetime.now().strftime("%H:%M:%S")
    print(f"[{tm}] CLIConductor starting on {host}:{port}")

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    server.run()
