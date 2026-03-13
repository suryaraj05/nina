#!/usr/bin/env python3
"""
Startup script for Nina backend that fixes Windows asyncio issues
"""
import asyncio
import sys
import uvicorn

if sys.platform == "win32":
    # Set ProactorEventLoop policy for Windows (supports subprocesses)
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

