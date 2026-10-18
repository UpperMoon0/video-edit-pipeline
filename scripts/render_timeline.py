#!/usr/bin/env python3
"""Validate, inspect, or render a versioned timeline without modifying inputs."""
import argparse
import json
from pathlib import Path
from pipeline.common import PipelineError
from pipeline.timeline import load_timeline
from pipeline.renderer import render, command_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('timeline', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--validate', action='store_true', help='Validate structure and paths; no FFmpeg required')
    modes.add_argument('--preflight', action='store_true', help='Also probe stream types and source ranges')
    modes.add_argument('--dry-run', action='store_true', help='Inspect commands and graphs without writing files')
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--cache-mib', type=int, default=1024)
    parser.add_argument('--no-overwrite', action='store_true')
    args = parser.parse_args()
    try:
        if args.cache_mib < 0:
            raise PipelineError('cache_budget', 'cache-mib', 'Cache budget must be nonnegative.')
        timeline = load_timeline(args.timeline, media=args.preflight)
        if args.validate or args.preflight:
            result = {'valid': True, 'mode': 'media-preflight' if args.preflight else 'structural-validation',
                'duration': timeline.duration, 'fps': str(timeline.fps), 'frames': sum(timeline.frames)}
        elif args.dry_run:
            result = command_plan(timeline)
        else:
            result = render(timeline, cache_enabled=not args.no_cache, cache_bytes=args.cache_mib * 1024 * 1024, overwrite=not args.no_overwrite)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except PipelineError as exc:
        print(json.dumps({'ok': False, 'error': exc.as_dict()}))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({'ok': False, 'error': {'code': 'cancelled', 'message': 'Interrupted; previous output preserved.'}}))
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
