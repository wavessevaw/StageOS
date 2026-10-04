"""Tauri launches this bundled process; no user terminal or Python required."""

import os, sys, argparse
from pathlib import Path
import uvicorn
from backend.app import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--test-no-auth", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    from backend.network import create_desktop_app
    uvicorn.run(
        create_app() if args.test_no_auth else create_desktop_app(),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
