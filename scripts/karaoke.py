#!/usr/bin/env python3
"""Local karaoke production: reusable projects, alignment, design and instrumental delivery."""
import argparse
import json
from pathlib import Path
from pipeline.common import PipelineError


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('source', type=Path)
    init.add_argument('project', type=Path)
    init.add_argument('--title', required=True)
    for name in ('build', 'align', 'render', 'preview'):
        c = commands.add_parser(name)
        c.add_argument('project', type=Path)
        if name == 'align':
            c.add_argument('--model', default='small')
            c.add_argument('--allow-download', action='store_true')
            c.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
        if name in ('render', 'preview'):
            c.add_argument('output', type=Path)
            c.add_argument('--encoder', choices=['libx264', 'h264_nvenc'], default='libx264')
        if name == 'preview':
            c.add_argument('--start', type=float, required=True)
            c.add_argument('--duration', type=float, required=True)
    remux = commands.add_parser('remux')
    remux.add_argument('video', type=Path)
    remux.add_argument('audio', type=Path)
    remux.add_argument('output', type=Path)
    sep = commands.add_parser('separate')
    sep.add_argument('source', type=Path)
    sep.add_argument('output', type=Path)
    sep.add_argument('--model', type=Path, required=True)
    sep.add_argument('--model-data', type=Path, required=True)
    sep.add_argument('--provider', choices=['cpu', 'directml', 'cuda'], default='cpu')
    args = p.parse_args(argv)
    try:
        from pipeline import karaoke
        if args.command == 'init':
            result = karaoke.initialize(args.source, args.project, args.title)
        elif args.command == 'build':
            result = karaoke.build(args.project)
        elif args.command == 'align':
            from pipeline.karaoke_alignment import align
            result = align(args.project, model=args.model, allow_download=args.allow_download, device=args.device)
        elif args.command == 'separate':
            from pipeline.karaoke_separation import separate
            if args.output.suffix.lower() != '.wav':
                raise PipelineError('karaoke_audio_format', 'output', 'The separated master must use a .wav extension.')
            result = separate(args.source, args.output, args.model, args.model_data, provider=args.provider)
        elif args.command == 'remux':
            result = karaoke.remux(args.video, args.audio, args.output)
        else:
            result = karaoke.render(args.project, args.output, encoder=args.encoder,
                start=getattr(args, 'start', None), duration=getattr(args, 'duration', None))
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=True))
        return 0
    except (PipelineError, OSError, ValueError, KeyError, RuntimeError) as exc:
        error = exc.as_dict() if isinstance(exc, PipelineError) else {'code': 'karaoke_failed', 'message': str(exc)}
        print(json.dumps({'ok': False, 'error': error}, ensure_ascii=True))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({'ok': False, 'error': {'code': 'cancelled', 'message': 'Interrupted; previous outputs were preserved.'}}))
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
