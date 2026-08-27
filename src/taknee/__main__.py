"""Kernel entrypoint: `uv run taknee` serves the loopback API."""

from __future__ import annotations

import argparse

from . import catalog


def main() -> None:
    parser = argparse.ArgumentParser(prog="taknee", description="Huginn & Muninn kernel")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47821)
    args = parser.parse_args()

    catalog.assert_catalog_compliance()  # fail fast on any >80B entry

    import uvicorn
    from .api import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
