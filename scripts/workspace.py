#!/usr/bin/env python3
"""Serve a private editing workspace with the pipeline's shared browser UI."""
import argparse
import json
from pathlib import Path
from pipeline.workspace import Workspace, serve
from pipeline.common import PipelineError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='Workspace project.json (or its directory)')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--describe', action='store_true', help='Validate and print project details without starting a server')
    args = parser.parse_args()
    try:
        workspace = Workspace(args.project)
        if args.describe:
            try:
                print(json.dumps(workspace.public_project(), ensure_ascii=True))
            finally:
                workspace.close()
        else:
            serve(workspace, args.port)
    except (OSError, ValueError, PipelineError) as exc:
        parser.exit(1, f'Workspace could not start: {exc}\n')


if __name__ == '__main__':
    main()
