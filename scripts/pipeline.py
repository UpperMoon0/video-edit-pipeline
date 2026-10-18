#!/usr/bin/env python3
"""Stable JSON CLI for local jobs, editing, footage evidence and delivery."""
import argparse
import json
import sys
from pathlib import Path
from pipeline.common import PipelineError, read_json, FileLock


def parser():
    root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=root)
    p.add_argument('--config', type=Path)
    commands = p.add_subparsers(dest='command', required=True)
    for name in ('setup', 'discover', 'latest-ready'):
        commands.add_parser(name)
    d = commands.add_parser('doctor')
    d.add_argument('--human', action='store_true')
    w = commands.add_parser('watch')
    w.add_argument('--once', action='store_true')
    i = commands.add_parser('ingest')
    i.add_argument('source', type=Path)
    r = commands.add_parser('resume')
    r.add_argument('job', type=Path)
    r.add_argument('--source', type=Path)
    for name in ('job-status', 'retry', 'cancel', 'quarantine'):
        command = commands.add_parser(name)
        command.add_argument('job')
    l = commands.add_parser('jobs-list')
    l.add_argument('--status')
    l.add_argument('--limit', type=int, default=100)
    l.add_argument('--offset', type=int, default=0)
    e = commands.add_parser('edit')
    e.add_argument('timeline', type=Path)
    e.add_argument('--expected-revision', type=int, required=True)
    e.add_argument('--operation', type=Path, required=True, help='JSON operation file')
    t = commands.add_parser('timeline-get')
    t.add_argument('timeline', type=Path)
    v = commands.add_parser('preview')
    v.add_argument('timeline', type=Path)
    v.add_argument('--start', type=float, required=True)
    v.add_argument('--end', type=float, required=True)
    v.add_argument('--output', type=Path)
    for name in ('validate', 'render'):
        command = commands.add_parser(name)
        command.add_argument('timeline', type=Path)
        if name == 'validate':
            command.add_argument('--media', action='store_true')
        else:
            command.add_argument('--job', help='Attach delivery progress/cancellation to a registered job')
            command.add_argument('--no-cache', action='store_true')
    s = commands.add_parser('sample')
    s.add_argument('source', type=Path)
    s.add_argument('output', type=Path)
    for name, value in [('interval', 10), ('start', 0), ('end', 0)]:
        s.add_argument('--' + name, type=float, default=value)
    for name, value in [('columns', 4), ('rows', 4), ('width', 320)]:
        s.add_argument('--' + name, type=int, default=value)
    s.add_argument('--count', type=int)
    index = commands.add_parser('index')
    index.add_argument('source', type=Path)
    index.add_argument('--index', type=Path, required=True)
    index.add_argument('--transcript', type=Path)
    index.add_argument('--samples', type=Path)
    index.add_argument('--threshold', type=float, default=.3)
    q = commands.add_parser('query')
    q.add_argument('--index', type=Path, required=True)
    q.add_argument('--text', default='')
    q.add_argument('--kind', choices=['transcript', 'shot', 'sample'], default='transcript')
    q.add_argument('--asset-id')
    q.add_argument('--start', type=float)
    q.add_argument('--end', type=float)
    q.add_argument('--limit', type=int, default=20)
    q.add_argument('--offset', type=int, default=0)
    c = commands.add_parser('convert-scaffold')
    c.add_argument('source', type=Path)
    c.add_argument('destination', type=Path)
    return p


def dispatch(args):
    from pipeline.operations import config_read, discover, doctor, watch
    from pipeline.state import JobStore
    name, root = args.command, args.root.resolve()
    config_path = args.config or root / 'config.json'
    if name == 'doctor':
        return doctor(root, config_path)
    if name in ('setup', 'discover', 'ingest', 'resume', 'watch', 'retry'):
        config = config_read(config_path)
    if name == 'setup':
        for folder in [root / 'jobs', root / 'state', root / 'logs', *map(Path, config['inbox_paths'])]:
            folder.mkdir(parents=True, exist_ok=True)
        JobStore(root)
        return {'version': 1, 'status': 'initialized', 'doctor': doctor(root, config_path)}
    if name == 'discover':
        return {'version': 1, 'items': discover(config)}
    if name == 'watch':
        return watch(root, config_path, args.once)
    if name in ('ingest', 'resume', 'retry', 'quarantine'):
        from pipeline.jobs import ingest, resume_job, retry_job, quarantine_job
        if name == 'ingest':
            return ingest(root, args.source, config)
        if name == 'resume':
            return resume_job(root, args.job, config, args.source)
        if name == 'retry':
            return retry_job(root, args.job, config)
        return quarantine_job(root, args.job)
    if name in ('jobs-list', 'job-status', 'latest-ready', 'cancel'):
        store = JobStore(root)
        if name == 'jobs-list':
            items = store.list(args.status, args.limit, args.offset)
            return {'version': 1, 'items': items, 'next_offset': args.offset + len(items) if len(items) == args.limit else None}
        if name == 'latest-ready':
            return store.latest_ready()
        return store.request_cancel(args.job) if name == 'cancel' else store.get(args.job)
    if name in ('edit', 'convert-scaffold'):
        from pipeline.editing import edit_timeline, convert_scaffold
        return edit_timeline(args.timeline, args.expected_revision, read_json(args.operation)) if name == 'edit' else convert_scaffold(args.source, args.destination)
    if name == 'preview':
        from pipeline.preview import preview
        return preview(args.timeline, args.start, args.end, args.output)
    if name in ('timeline-get', 'validate', 'render'):
        from pipeline.timeline import load_timeline
        timeline = load_timeline(args.timeline, media=name == 'render' or getattr(args, 'media', False))
        if name != 'render':
            return {'version': 1, 'valid': True, 'duration': timeline.duration, 'frames': sum(timeline.frames), 'timeline': timeline.spec}
        from pipeline.renderer import render
        if not args.job:
            return render(timeline, cache_enabled=not args.no_cache)
        store = JobStore(root)
        row = store.get(args.job)
        job = Path(row['job_path'])
        if not args.timeline.resolve().is_relative_to(job):
            raise PipelineError('job_timeline', 'timeline', 'Attached render must use a timeline inside the registered job.')
        with FileLock(job.with_name('.' + job.name + '.job.lock')):
            store.update(row['id'], status='processing', stage='render', cancel_requested=0, error=None)
            try:
                result = render(timeline, cache_enabled=not args.no_cache,
                    cancel=lambda: bool(store.get(row['id'])['cancel_requested']))
                store.finish_ready(row['id'], row['prepared_at'])
                store.update(row['id'], stage='render-complete')
                return result
            except (Exception, KeyboardInterrupt) as exc:
                (job / 'READY.txt').unlink(missing_ok=True)
                store.update(row['id'], status='cancelled' if store.get(row['id'])['cancel_requested'] else 'failed',
                    stage='render-failed', error=exc.as_dict() if isinstance(exc, PipelineError) else {'code': 'render_error', 'message': str(exc)})
                raise
    if name == 'sample':
        from pipeline.sampling import sample_video
        return sample_video(args.source, args.output, **{key: getattr(args, key) for key in ('interval', 'start', 'end', 'columns', 'rows', 'width', 'count')})
    if name == 'index':
        from pipeline.footage import build_index
        return build_index(args.source, args.index, transcript=args.transcript, samples=args.samples, threshold=args.threshold)
    if name == 'query':
        from pipeline.footage import query_index
        return query_index(args.index, **{key: getattr(args, key) for key in ('text', 'kind', 'asset_id', 'start', 'end', 'limit', 'offset')})
    raise AssertionError(name)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        failed = result.get('status') in ('failed', 'quarantined', 'cancelled', 'stale') or result.get('ready') is False
        if args.command == 'doctor' and args.human:
            for check in result['checks']:
                print(('OK' if check['ok'] else 'FAIL' if check['required'] else 'OPTIONAL') + ' ' + check['name'] + ': ' + json.dumps(check['detail']))
        else:
            print(json.dumps({'ok': not failed, 'result': result}, ensure_ascii=True))
        return 1 if failed else 0
    except (PipelineError, OSError, ValueError, KeyError) as exc:
        error = exc.as_dict() if isinstance(exc, PipelineError) else {'code': 'operation_failed', 'message': str(exc)}
        print(json.dumps({'ok': False, 'error': error}, ensure_ascii=True))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({'ok': False, 'error': {'code': 'cancelled', 'message': 'Interrupted; published inputs and outputs were preserved.'}}))
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
