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
from .common import read_json, write_json, digest, FileLock, PipelineError
from .editing import edit_timeline
from .timeline import finite_tree, load_timeline, normalize

WEB = Path(__file__).with_name('web')
CLI = Path(__file__).resolve().parents[1] / 'pipeline.py'
PATH = {'type': 'string', 'minLength': 1, 'pattern': '^[^\u0000\r\n]+$'}
TEXT = {'type': 'string'}
WORKSPACE_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'title': 'Video Edit Pipeline single-timeline workspace v2',
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'version': {'const': 2}, 'title': {'type': 'string', 'minLength': 1},
        'subtitle': TEXT, 'media_root': PATH, 'timeline': PATH,
        'render': {'type': 'object', 'additionalProperties': False,
            'properties': {'source': PATH, 'timeline_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}},
            'required': ['source', 'timeline_sha256']}},
    'required': ['version', 'title', 'media_root', 'timeline']}


def project_path(path):
    path = Path(path).resolve()
    return path / 'project.json' if path.is_dir() else path


def validate_project(project):
    finite_tree(project)
    if project.get('version') == 1:
        raise ValueError('Workspace v1 has independent cut/storyboard/script data. Migrate the chosen edit into one timeline; see docs/WORKSPACE.md.')
    errors = list(Draft202012Validator(WORKSPACE_SCHEMA).iter_errors(project))
    if errors:
        error = errors[0]
        raise ValueError(f'Invalid workspace {".".join(map(str, error.path))}: {error.message}')


def initialize(timeline_path, destination, *, script=None, master=None, title=None,
               media_root=None, narration=None):
    """Bind one canonical timeline; explicit narration imports live on its clips."""
    timeline_path = Path(timeline_path).resolve()
    timeline = load_timeline(timeline_path)
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Workspace already exists; its current edit was preserved.')
    root = Path(media_root).resolve() if media_root else timeline.base
    if not destination.is_relative_to(root):
        raise ValueError('Workspace directory must be inside media_root. Select --media-root explicitly.')
    def checked(path):
        path = Path(path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Asset must be a file inside media_root: {path}. Select --media-root explicitly.')
        return str(path)
    checked(timeline_path)
    for path in timeline.assets():
        checked(path)
    if not timeline.output.is_relative_to(root):
        raise ValueError('Timeline output must remain inside media_root.')
    if master:
        checked(master)
    if script and narration:
        raise ValueError('Use one narration import: --script for one clip, or --narration for per-clip text.')
    texts = None
    if script:
        if len(timeline.frames) != 1:
            raise ValueError('A multi-scene script needs explicit per-clip text. Use --narration with one string per clip.')
        texts = [Path(checked(script)).read_text(encoding='utf-8-sig')]
    if narration:
        texts = read_json(checked(narration))
    if texts is not None:
        if master:
            raise ValueError('Import narration first, then verify an export of that timeline before binding --master.')
        if not isinstance(texts, list) or len(texts) != len(timeline.frames) or any(not isinstance(t, str) for t in texts):
            raise ValueError('Narration must be a JSON array with one string per timeline clip.')
        with FileLock(timeline_path.with_name('.' + timeline_path.name + '.edit.lock'), timeout=30):
            current = load_timeline(timeline_path)
            if digest(current.spec) != digest(timeline.spec):
                raise ValueError('Timeline changed during initialization. Retry with the latest edit.')
            for clip, text in zip(timeline.spec['clips'], texts):
                if clip.get('editorial', {}).get('text') != text and clip.get('editorial', {}).get('narration_status') == 'recorded':
                    clip['audio'] = {'mode': 'mute'}
                clip.setdefault('editorial', {}).update(text=text, narration_status='pending' if text else 'none')
            audio = timeline.spec.get('audio', {})
            if audio.pop('voiceover', None):
                for key in ('voiceover_start', 'voiceover_source_in', 'voiceover_volume', 'ducking'):
                    audio.pop(key, None)
                if timeline.spec.get('captions', {}).get('kind') == 'narration':
                    timeline.spec.pop('captions')
            timeline.spec['revision'] += 1
            timeline = normalize(timeline.spec, timeline.base, path=timeline_path)
            write_json(timeline_path, timeline.spec)
    project = dict(version=2, title=title or timeline.spec.get('metadata', {}).get('title') or timeline_path.stem,
                   media_root=str(root), timeline=str(timeline_path))
    if master:
        project['render'] = dict(source=checked(master), timeline_sha256=digest(timeline.spec))
    validate_project(project)
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / 'project.json'
    write_json(path, project)
    return {'project': str(path), 'scenes': len(timeline.frames), 'duration': timeline.duration}


class Workspace:
    def __init__(self, path):
        self.path = project_path(path)
        self.project = read_json(self.path)
        validate_project(self.project)
        self.root = (self.path.parent / self.project['media_root']).resolve()
        if not self.root.is_dir() or not self.path.is_relative_to(self.root):
            raise ValueError('Workspace manifest must be inside its media_root directory.')
        self.timeline = self.resolve(self.project['timeline'])
        self.assets = {}
        self.tasks = {}
        self.lock = threading.RLock()
        self.current()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def resolve(self, value):
        path = (self.path.parent / value).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError(f'Workspace asset is missing or outside media_root: {path}')
        return path

    def check_timeline(self, timeline):
        for asset in timeline.assets():
            self.resolve(asset)
        if not timeline.output.is_relative_to(self.root):
            raise ValueError('Timeline output must remain inside media_root.')

    def current(self):
        timeline = load_timeline(self.resolve(self.timeline))
        self.check_timeline(timeline)
        return timeline

    def asset(self, path):
        path = self.resolve(path)
        key = hashlib.sha256(str(path).encode()).hexdigest()[:24]
        self.assets[key] = path
        return '/media/' + key

    def public_project(self):
        with self.lock:
            timeline = self.current()
            fingerprint = digest(timeline.spec)
            scenes, offset = [], 0
            for clip, frames in zip(timeline.spec['clips'], timeline.frames):
                editorial = clip.get('editorial', {})
                scenes.append(dict(id=clip['id'], title=editorial.get('title') or clip['id'],
                    text=editorial.get('text', ''), notes=editorial.get('notes', ''),
                    visual_status=editorial.get('visual_status', 'ready'),
                    narration_status=editorial.get('narration_status', 'pending' if editorial.get('text') else 'none'),
                    start=float(Fraction(offset) / timeline.fps), duration=float(Fraction(frames) / timeline.fps),
                    media=self.asset(timeline.asset(clip['source'])), media_in=clip['in'],
                    media_type=clip['type'], audio_mode=clip['audio']['mode']))
                offset += frames
            master = None
            cached = self.project.get('render')
            if cached and cached['timeline_sha256'] == fingerprint:
                # Reusing an export filename must not reuse a video's in-memory
                # buffer after a picture edit. no-store does not clear that buffer.
                master = self.asset(cached['source']) + '?edit=' + fingerprint
            audio = timeline.spec.get('audio', {})
            timed = bool(timeline.spec.get('titles') or timeline.spec.get('overlays') or
                         audio.get('voiceover') or audio.get('music') or audio.get('sfx') or timeline.spec.get('captions'))
            return dict(version=2, title=self.project['title'], subtitle=self.project.get('subtitle', ''),
                duration=timeline.duration, scenes=scenes, master=master,
                revision=timeline.spec['revision'], timeline_sha256=fingerprint,
                can_preview=True, can_reorder=not timed,
                render_stale=bool(cached and master is None),
                workspace_id=hashlib.sha256(str(self.path).encode()).hexdigest())

    def script_text(self):
        project = self.public_project()
        return '\n\n'.join(f"{s['title']}\n\n{s['text']}" for s in project['scenes'] if s['text'].strip())

    def edit(self, expected_revision, operation):
        if type(expected_revision) is not int or expected_revision < 0 or not isinstance(operation, dict):
            raise ValueError('Supply the timeline revision and an edit operation.')
        if operation.get('op') not in ('editorial', 'trim', 'reorder', 'undo'):
            raise ValueError('Unsupported workspace edit.')
        with self.lock:
            if operation['op'] == 'reorder' and not self.public_project()['can_reorder']:
                raise ValueError('This edit has timed audio/graphics. Reorder their anchors explicitly through the timeline editor first.')
            edit_timeline(self.resolve(self.timeline), expected_revision, operation, validator=self.check_timeline)
            return self.public_project()

    def preview(self, start, end, expected_hash):
        with self.lock:
            timeline = self.current()
            fingerprint = digest(timeline.spec)
            if expected_hash != fingerprint:
                raise ValueError('Timeline changed. Reload the current edit before building a preview.')
            if any(type(x) not in (int, float) for x in (start, end)) or not (0 <= start < end <= timeline.duration and end-start <= 30):
                raise ValueError('Choose a range of up to 30 seconds inside the edit.')
            if any(t['status'] in ('queued', 'rendering') for t in self.tasks.values()):
                raise ValueError('A preview is already building. Wait for it to finish.')
            if len(self.tasks) >= 100:
                raise ValueError('This session has reached 100 previews. Restart the workspace for a new session.')
            key = uuid.uuid4().hex
            directory = self.path.parent / 'previews'
            if not directory.resolve().is_relative_to(self.root):
                raise ValueError('Preview directory is outside media_root.')
            directory.mkdir(exist_ok=True)
            # Freeze this edit before queuing. Saves during rendering cannot change it.
            spec = copy.deepcopy(timeline.spec)
            for clip in spec['clips']:
                clip['source'] = str(timeline.asset(clip['source']))
                if clip.get('transcript'):
                    clip['transcript'] = str(timeline.asset(clip['transcript']))
            for group in ('overlays', 'titles'):
                for item in spec.get(group, []):
                    for field in ('source', 'font'):
                        if item.get(field): item[field] = str(timeline.asset(item[field]))
            audio = spec.get('audio', {})
            if audio.get('voiceover'): audio['voiceover'] = str(timeline.asset(audio['voiceover']))
            for kind in ('music', 'sfx'):
                for track in audio.get(kind, []): track['source'] = str(timeline.asset(track['source']))
            if spec.get('captions', {}).get('transcript'):
                spec['captions']['transcript'] = str(timeline.asset(spec['captions']['transcript']))
            spec['output'] = str(timeline.output)
            snapshot = directory / (key + '.json')
            write_json(snapshot, spec)
            self.tasks[key] = dict(status='queued', start=start, end=end,
                revision=timeline.spec['revision'], timeline_sha256=fingerprint)
            self.pool.submit(self.render, key, start, end, snapshot)
        return key

    def render(self, key, start, end, snapshot):
        output = snapshot.with_suffix('.mp4')
        with self.lock:
            self.tasks[key]['status'] = 'rendering'
        try:
            timeline = load_timeline(self.resolve(snapshot))
            self.check_timeline(timeline)
            process = subprocess.run([sys.executable, str(CLI), 'preview', str(snapshot),
                '--start', str(start), '--end', str(end), '--output', str(output)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            envelope = json.loads(process.stdout)
            if process.returncode or not envelope.get('ok') or not output.is_file():
                raise ValueError(str(envelope.get('error', 'Preview failed')))
            with self.lock:
                self.tasks[key].update(status='ready', media=self.asset(output))
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
                try:
                    return self.json(workspace.public_project())
                except (ValueError, OSError, PipelineError) as exc:
                    return self.json({'error': str(exc)}, 409)
            if path == '/api/script':
                try:
                    return self.json({'text': workspace.script_text()})
                except (ValueError, OSError, UnicodeError, PipelineError) as exc:
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
            if self.path not in ('/api/preview', '/api/edit'):
                return self.json({'error': 'Not found'}, 404)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 131072 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Invalid request size')
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Expected a JSON object.')
                if self.path == '/api/edit':
                    return self.json(workspace.edit(body.get('expected_revision'), body.get('operation')))
                key = workspace.preview(body.get('start'), body.get('end'), body.get('timeline_sha256'))
                return self.json({'task': key}, 202)
            except PipelineError as exc:
                return self.json({'error': str(exc), 'code': exc.code}, 409 if exc.code == 'stale_revision' else 400)
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
