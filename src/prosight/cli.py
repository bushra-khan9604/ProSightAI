"""Command-line entry points for database setup, queries, and the web server."""

from __future__ import annotations

import argparse
import json
import sys

from .agent import ProSightAgent
from .repository import ProjectRepository


def main() -> None:
    """Parse the requested command and invoke the corresponding ProSight service."""
    parser = argparse.ArgumentParser(description="ProSight AI project insights agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Load sample JSON into SQLite")
    ask = sub.add_parser("ask", help="Ask a project question")
    ask.add_argument("query")
    ask.add_argument("--role", default="project_manager")
    host = sub.add_parser("serve", help="Start the JSON HTTP API")
    host.add_argument("--host", default="127.0.0.1")
    host.add_argument("--port", type=int, default=8000)
    migrate = sub.add_parser("migrate-supabase", help="Copy legacy SQLite data to Supabase")
    migrate.add_argument("--sqlite", default=None, help="Legacy SQLite database path")
    migrate.add_argument("--dry-run", action="store_true", help="Validate without remote writes")
    args = parser.parse_args()
    if args.command == "init":
        ProjectRepository().initialize()
        print("Sample database initialized.")
    elif args.command == "ask":
        print(json.dumps(ProSightAgent().ask(args.query, args.role), indent=2))
    elif args.command == "migrate-supabase":
        from .migration import SupabaseMigrator
        result = SupabaseMigrator(args.sqlite or ProjectRepository().db_path, args.dry_run).run()
        print(json.dumps(result, indent=2, default=str))
    else:
        try:
            # Import the web stack only for `serve`, so database/CLI commands remain usable.
            from .api import serve
        except ModuleNotFoundError as error:
            dependency = error.name or "a required package"
            print(
                f"Cannot start ProSight because '{dependency}' is not installed.\n"
                "Install this project's dependencies in the active environment:\n"
                "    python -m pip install -e .",
                file=sys.stderr,
            )
            raise SystemExit(1) from error
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
