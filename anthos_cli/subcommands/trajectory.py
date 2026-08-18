"""``anthos trajectory`` subcommand — launch the session trajectory viewer."""

from __future__ import annotations

from typing import Callable


def build_trajectory_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "trajectory",
        help="Open the session trajectory viewer in your browser",
        description=(
            "Launches a local web UI for inspecting agent session trajectories — "
            "every message, tool call, reasoning block, and token count, all in one view."
        ),
    )
    p.add_argument(
        "--port",
        type=int,
        default=9121,
        metavar="PORT",
        help="Port to listen on (default: 9121)",
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        help="Don't automatically open a browser tab",
    )
    p.set_defaults(func=_cmd_trajectory)


def _cmd_trajectory(args) -> None:
    from anthos_cli.trajectory_server import serve
    serve(port=args.port, open_browser=not args.no_open)
