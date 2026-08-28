"""Taknee CLI — Sovereign Agentic Kernel & Free-Tier Compute Swarm."""

from __future__ import annotations

import argparse
import sys

from . import catalog


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="taknee",
        description="Huginn & Muninn — Sovereign AI Coding Agent & Free-Tier Compute Swarm",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Serve command (default)
    serve_parser = subparsers.add_parser("serve", help="Start the background kernel API server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=47821)

    # Setup command
    subparsers.add_parser("setup", help="Interactive first-run wizard to configure free AI API keys")

    # Doctor command
    subparsers.add_parser("doctor", help="Inspect live health and quotas across all free providers")

    # Deals command
    deals_parser = subparsers.add_parser("deals", help="Scan Reddit, HN, and OpenRouter for free API drops")
    deals_parser.add_argument("--refresh", action="store_true", help="Force fresh web scan")

    # Models command
    models_parser = subparsers.add_parser("models", help="List active zero-cost and free-tier models")
    models_parser.add_argument("--refresh", action="store_true", help="Force live gateway probe")

    # Global flags if no subcommand passed
    parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=47821, help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.command == "setup":
        from .cli.setup import run_setup
        run_setup()
        return

    if args.command == "doctor":
        from .cli.setup import run_doctor
        print("🔍 Checking Taknee Provider Health Matrix:\n")
        run_doctor()
        return

    if args.command == "deals":
        from .radar.community_feed import CommunityFeedScraper
        print("🎯 Scanning for free AI API deals (Reddit, Hacker News, OpenRouter)...")
        scraper = CommunityFeedScraper()
        deals = scraper.get_deals(force_refresh=args.refresh)
        if not deals:
            print("No new promotional drops found right now. Check back soon!")
            return
        print(f"\nFound {len(deals)} active community deal discussions:\n")
        for d in deals[:10]:
            prov = f"[{d.provider_hint.upper()}] " if d.provider_hint else ""
            cred = f" ({d.credits_hint})" if d.credits_hint else ""
            print(f"  ⚡ {prov}{d.title}{cred}")
            print(f"     Source: {d.source} · {d.url}\n")
        return

    if args.command == "models":
        from .swarm.radar import Radar
        print("⚡ Probing active zero-cost and free-tier models...")
        radar = Radar()
        models = radar.get_free_models(force_refresh=args.refresh)
        print(f"\n{'PROVIDER':<14} {'SPEED':<10} {'CONTEXT':<10} {'MODEL ID'}")
        print("─" * 70)
        for m in models:
            ctx_k = f"{m.context_window // 1024}k"
            spd = f"{m.speed_tps:.0f} t/s"
            print(f"{m.provider:<14} {spd:<10} {ctx_k:<10} {m.id}")
        return

    # Default: serve
    catalog.assert_catalog_compliance()  # fail fast on any >80B entry

    import uvicorn
    from .api import app

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 47821)
    print(f"⚡ Huginn & Muninn Kernel v2 running on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()

