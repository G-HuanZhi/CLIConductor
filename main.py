#!/usr/bin/env python
"""CLIConductor — entry point."""

from src.server import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8767, log_level="info")
