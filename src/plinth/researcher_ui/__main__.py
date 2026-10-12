"""CLI entry point: python -m plinth.researcher_ui"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plinth Pipeline Researcher UI")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root containing data/pipeline/runs/",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Runs directory relative to the project root (default: DataLayout().runs_dir)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default: loopback only). The UI has no authentication.",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    project_root = args.project_root.resolve()

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Researcher UI requires optional dependencies. Install with: "
            'pip install "plinth[ui] @ git+https://github.com/cbrady321/plinth.git@v0.5.0"'
        ) from exc

    from plinth.layout import DataLayout
    from plinth.researcher_ui.app import create_app

    layout = DataLayout(runs_dir=args.runs_dir) if args.runs_dir else None
    if args.host in LOOPBACK_HOSTS:
        # Only answer requests addressed to this machine, so a web page cannot reach the UI by DNS rebinding.
        app = create_app(project_root, layout=layout, allowed_hosts=list(LOOPBACK_HOSTS))
    else:
        print(
            f"WARNING: binding to {args.host}. The researcher UI has no authentication; anyone who can reach "
            "this address can read every run under the runs directory.",
            file=sys.stderr,
        )
        app = create_app(project_root, layout=layout)
    print(f"Plinth Researcher UI at http://{args.host}:{args.port} (project_root={project_root})")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
