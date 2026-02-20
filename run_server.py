#!/usr/bin/env python3
"""
HTTP server entry point for the Lecture-to-Notes Pipeline API.

Usage:
    python run_server.py
    python run_server.py --host 0.0.0.0 --port 8080
    python run_server.py --reload   # Development mode

API docs available at:
    http://localhost:8000/docs       (Swagger UI)
    http://localhost:8000/redoc      (ReDoc)
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lecture-to-Notes Pipeline API Server",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of uvicorn workers (default: 1)",
    )

    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required. Install with: pip install -e '.[api]'")
        return 1

    uvicorn.run(
        "lecture_agents.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
