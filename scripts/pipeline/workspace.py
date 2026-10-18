"""Project-driven, loopback-only review UI. No project assets are bundled."""
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import copy
import hashlib
import json
import mimetypes
import re
import subprocess
import sys
import threading
import uuid

from jsonschema import Draft202012Validator
from .common import read_json
from .timeline import finite_tree, load_timeline

WEB = Path(__file__).with_name('web')
CLI = Path(__file__).resolve().parents[1] / 'pipeline.py'
PATH = {'type': 'string', 'minLength': 1, 'pattern': '^[^\u0000\r\n]+$'}
TEXT = {'type': 'string'}
NUMBER = {'type': 'number', 'minimum': 0}
SCENE = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'id': PATH, 'title': TEXT, 'text': TEXT, 'start': NUMBER,
                   'duration': {'type': 'number', 'exclusiveMinimum': 0},
                   'media': {'type': ['string', 'null']}, 'media_in': NUMBER,
                   'media_type': {'enum': ['video', 'image']}},
    'required': ['id', 'title', 'text', 'start', 'duration', 'media', 'media_in']}
WORKSPACE_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'title': 'Video Edit Pipeline review workspace v1',
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'version': {'const': 1}, 'title': {'type': 'string', 'minLength': 1},
        'subtitle': TEXT, 'media_root': PATH, 'timeline': PATH, 'script': PATH,
        'master': {'type': ['string', 'null']},
        'duration': {'type': 'number', 'exclusiveMinimum': 0},
        'scenes': {'type': 'array', 'items': SCENE, 'minItems': 1},
        'storyboard': {'type': 'array', 'items': SCENE},
        'assets': {'type': 'object', 'propertyNames': {'pattern': '^[A-Za-z0-9_-]+$'},
                   'additionalProperties': PATH}},
    'required': ['version', 'title', 'media_root', 'duration', 'scenes', 'assets']}


def project_path(path):
    path = Path(path).resolve()
    return path / 'project.json' if path.is_dir() else path


def validate_project(project):
    finite_tree(project)
    errors = list(Draft202012Validator(WORKSPACE_SCHEMA).iter_errors(project))
    if errors:
        error = errors[0]
        raise ValueError(f'Invalid workspace {".".join(map(str, error.path))}: {error.message}')
    def media(value):
        if value is not None and (not value.startswith('/media/') or value[7:] not in project['assets']):
            raise ValueError('Scene/master media must reference a registered /media/asset-id.')
    media(project.get('master'))
    for group in ('scenes', 'storyboard'):
        ids = set()
        end = 0
        for scene in project.get(group, []):
            if scene['id'] in ids:
                raise ValueError('Scene IDs must be unique within each view.')
            ids.add(scene['id'])
            media(scene['media'])
            if group == 'scenes':
                if abs(scene['start'] - end) > .001:
                    raise ValueError('Cut scenes must cover the timeline sequentially without gaps.')
                end = scene['start'] + scene['duration']
        if group == 'scenes' and abs(end - project['duration']) > .001:
            raise ValueError('Scene durations must match the workspace duration.')


def initialize(timeline_path, destination, *, script=None, master=None, title=None,
               media_root=None, narration=None):
    """Create a manifest in a new directory, without rendering or copying media."""
    timeline_path = Path(timeline_path).resolve()
    timeline = load_timeline(timeline_path)
    destination = Path(destination).resolve()
    root = Path(media_root).resolve() if media_root else timeline.base
    if not destination.is_relative_to(root):
        raise ValueError('Workspace directory must be inside media_root. Select --media-root explicitly.')
    def checked(path):
        path = Path(path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Asset must be a file inside media_root: {path}. Select --media-root explicitly.')
        return str(path)
    texts = read_json(narration) if narration else [''] * len(timeline.frames)
    if not isinstance(texts, list) or len(texts) != len(timeline.frames) or any(not isinstance(t, str) for t in texts):
        raise ValueError('Narration must be a JSON array with one string per timeline clip.')
    assets = {}
    def asset(path):
        value = checked(path)
        key = next((k for k, v in assets.items() if v == value), None)
        if key is None:
            key = f'asset-{len(assets)}'
            assets[key] = value
        return '/media/' + key
    project = dict(version=1, title=title or timeline.spec.get('metadata', {}).get('title') or timeline_path.stem,
                   media_root=str(root), timeline=checked(timeline_path), duration=timeline.duration,
                   master=asset(master) if master else None, scenes=[], storyboard=[], assets=assets)
    if script:
        project['script'] = checked(script)
    for path in timeline.assets():
        checked(path)
    offset = 0
    for clip, frames, text in zip(timeline.spec['clips'], timeline.frames, texts):
        project['scenes'].append(dict(id=clip['id'], title=clip['id'], text=text,
            start=float(Fraction(offset) / timeline.fps), duration=float(Fraction(frames) / timeline.fps),
            media=asset(timeline.asset(clip['source'])), media_in=clip['in'], media_type=clip['type']))
        offset += frames
    validate_project(project)
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / 'project.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(project, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return {'project': str(path), 'scenes': len(project['scenes']), 'duration': timeline.duration}


class Workspace:
    def __init__(self, path):
        self.path = project_path(path)
        self.project = read_json(self.path)
        validate_project(self.project)
        self.root = (self.path.parent / self.project['media_root']).resolve()
        if not self.root.is_dir() or not self.path.is_relative_to(self.root):
            raise ValueError('Workspace manifest must be inside its media_root directory.')
        self.assets = {key: self.resolve(value) for key, value in self.project['assets'].items()}
        self.script = self.resolve(self.project['script']) if self.project.get('script') else None
        self.timeline = self.resolve(self.project['timeline']) if self.project.get('timeline') else None
        if self.timeline:
            timeline = load_timeline(self.timeline)
            if abs(timeline.duration - self.project['duration']) > .001:
                raise ValueError('Workspace duration differs from the timeline. Regenerate the manifest.')
            for asset in timeline.assets():
                self.resolve(asset)
        self.tasks = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def resolve(self, value):
        path = (self.path.parent / value).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError(f'Workspace asset is missing or outside media_root: {path}')
        return path

    def public_project(self):
        project = {k: v for k, v in self.project.items() if k not in ('assets', 'timeline', 'script', 'media_root')}
        project.update(has_script=self.script is not None, can_preview=self.timeline is not None,
                       workspace_id=hashlib.sha256(str(self.path).encode()).hexdigest())
        return project

    def preview(self, start, end):
        if not self.timeline:
            raise ValueError('No renderable timeline is configured.')
        if any(type(x) not in (int, float) for x in (start, end)) or not (0 <= start < end <= self.project['duration'] and end-start <= 30):
            raise ValueError('Choose a range of up to 30 seconds inside the edit.')
        with self.lock:
            if any(t['status'] in ('queued', 'rendering') for t in self.tasks.values()):
                raise ValueError('A preview is already building. Wait for it to finish.')
            if len(self.tasks) >= 100:
                raise ValueError('This session has reached 100 previews. Restart the workspace for a new session.')
            key = uuid.uuid4().hex
            self.tasks[key] = dict(status='queued', start=start, end=end)
            self.pool.submit(self.render, key, start, end)
        return key

    def render(self, key, start, end):
        output = self.path.parent / 'previews' / f'{key}.mp4'
        with self.lock:
            self.tasks[key]['status'] = 'rendering'
        try:
            # Check current paths again; a changed symlink or timeline cannot widen access.
            timeline = load_timeline(self.resolve(self.timeline))
            for asset in timeline.assets():
                self.resolve(asset)
            if abs(timeline.duration - self.project['duration']) > .001:
                raise ValueError('Timeline duration changed. Regenerate the workspace manifest.')
            if not output.resolve().is_relative_to(self.root):
                raise ValueError('Preview directory is outside media_root.')
            output.parent.mkdir(exist_ok=True)
            process = subprocess.run([sys.executable, str(CLI), 'preview', str(self.timeline),
                '--start', str(start), '--end', str(end), '--output', str(output)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            envelope = json.loads(process.stdout)
            if process.returncode or not envelope.get('ok') or not output.is_file():
                raise ValueError(str(envelope.get('error', 'Preview failed')))
            with self.lock:
                self.assets[key] = output
                self.tasks[key].update(status='ready', media='/media/' + key)
        except Exception as exc:
            with self.lock:
                self.tasks[key].update(status='failed', error=str(exc)[:1000])

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)


def handler(workspace):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def valid_request(self):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            origin = self.headers.get('Origin')
            return self.headers.get('Host') in allowed and (not origin or origin in {'http://' + x for x in allowed})

        def send_headers(self, status, mime, length, extra=None):
            self.send_response(status)
            for key, value in {'Content-Type': mime, 'Content-Length': str(length), 'Cache-Control': 'no-store',
                'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy':
                "default-src 'self'; media-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'", **(extra or {})}.items():
                self.send_header(key, value)
            self.end_headers()

        def json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_headers(status, 'application/json; charset=utf-8', len(body))
            if self.command != 'HEAD':
                self.wfile.write(body)

        def file(self, path, *, static=False):
            path = Path(path).resolve()
            root = WEB.resolve() if static else workspace.root
            if not path.is_relative_to(root) or not path.is_file():
                return self.json({'error': 'Asset unavailable'}, 404)
            size = path.stat().st_size
            start, end, status = 0, size-1, 200
            value = self.headers.get('Range')
            if value:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
                try:
                    if not match or not any(match.groups()):
                        raise ValueError()
                    a, b = match.groups()
                    if not a:
                        if int(b) == 0:
                            raise ValueError()
                        start = max(0, size-int(b))
                    else:
                        start = int(a)
                        end = min(size-1, int(b)) if b else size-1
                    if not 0 <= start <= end < size:
                        raise ValueError()
                except ValueError:
                    return self.send_headers(416, 'text/plain', 0, {'Content-Range': f'bytes */{size}'})
                status = 206
            headers = {'Accept-Ranges': 'bytes'}
            if status == 206:
                headers['Content-Range'] = f'bytes {start}-{end}/{size}'
            mime = {'js': 'text/javascript; charset=utf-8', 'css': 'text/css; charset=utf-8',
                    'html': 'text/html; charset=utf-8'}.get(path.suffix[1:]) or mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
            self.send_headers(status, mime, max(0, end-start+1), headers)
            if self.command == 'HEAD':
                return
            try:
                with path.open('rb') as stream:
                    stream.seek(start)
                    remaining = end-start+1
                    while remaining > 0:
                        chunk = stream.read(min(256*1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self.valid_request():
                return self.json({'error': 'Local workspace only'}, 403)
            path = self.path.split('?', 1)[0]
            if path == '/api/project':
                return self.json(workspace.public_project())
            if path == '/api/script':
                try:
                    if workspace.script is None:
                        raise ValueError('No full script configured for this workspace.')
                    return self.json({'text': workspace.resolve(workspace.script).read_text(encoding='utf-8-sig')})
                except (ValueError, OSError, UnicodeError) as exc:
                    return self.json({'error': str(exc)}, 404)
            if path.startswith('/api/tasks/'):
                with workspace.lock:
                    task = copy.deepcopy(workspace.tasks.get(path.rsplit('/', 1)[-1]))
                return self.json(task or {'error': 'Unknown preview'}, 200 if task else 404)
            if path.startswith('/media/'):
                with workspace.lock:
                    asset = workspace.assets.get(path[7:])
                return self.file(asset) if asset else self.json({'error': 'Unknown asset'}, 404)
            static = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
            if path in static:
                return self.file(WEB / static[path], static=True)
            return self.json({'error': 'Not found'}, 404)

        def do_POST(self):
            if not self.valid_request():
                return self.json({'error': 'Local workspace only'}, 403)
            if self.path != '/api/preview':
                return self.json({'error': 'Not found'}, 404)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Invalid request size')
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(size))
                key = workspace.preview(body.get('start'), body.get('end'))
                return self.json({'task': key}, 202)
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                return self.json({'error': str(exc)}, 400)
    return Handler


def serve(workspace, port=8766):
    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), handler(workspace))
        print(f'Video workspace: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        workspace.close()
