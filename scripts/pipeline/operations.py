"""Configuration, readiness diagnostics and a single-owner foreground watcher."""
import importlib.metadata
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from .common import FileLock, PipelineError, read_json, write_json, utcnow
from .media import tool, run

DEFAULTS = {'poll_seconds': 5, 'stable_seconds': 10, 'contact_sheet_frames': 16,
            'max_attempts': 3, 'retry_base_seconds': 30}


def config_read(path):
    value = read_json(Path(path))
    if not isinstance(value, dict):
        raise PipelineError('invalid_config', 'config', 'Configuration must be a JSON object.')
    config = {**DEFAULTS, **value}
    allowed = set(DEFAULTS) | {'inbox_paths', 'extensions'}
    if value.keys() - allowed:
        raise PipelineError('invalid_config', 'config', 'Unknown fields: ' + ', '.join(sorted(value.keys() - allowed)))
    for key in ('inbox_paths', 'extensions'):
        if not isinstance(config.get(key), list) or not config[key] or any(not isinstance(p, str) or not p for p in config[key]):
            raise PipelineError('invalid_config', key, 'Supply a nonempty array of nonempty strings.')
    for key in ('poll_seconds', 'stable_seconds', 'retry_base_seconds'):
        n = config[key]
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or n < (0 if key == 'stable_seconds' else .01):
            raise PipelineError('invalid_config', key, 'Use a finite positive number (stability may be zero).')
    for key, maximum in [('contact_sheet_frames', 4096), ('max_attempts', 100)]:
        n = config[key]
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= maximum:
            raise PipelineError('invalid_config', key, f'Use an integer from 1 to {maximum}.')
    if any(not extension.startswith('.') or '/' in extension or '\\' in extension for extension in config['extensions']):
        raise PipelineError('invalid_config', 'extensions', 'Use dot-prefixed file extensions, not paths.')
    base = Path(path).resolve().parent
    config['inbox_paths'] = [str((base / p).resolve()) for p in config['inbox_paths']]
    return config


def discover(config):
    extensions = {value.lower() for value in config['extensions']}
    result = []
    for folder in config['inbox_paths']:
        directory = Path(folder)
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in extensions:
                info = path.stat()
                result.append({'path': str(path.resolve()), 'size': info.st_size, 'mtime': info.st_mtime,
                               'stable': time.time() - info.st_mtime >= config['stable_seconds']})
    return sorted(result, key=lambda item: (item['mtime'], item['path']))


def doctor(root, config_path=None):
    root = Path(root).resolve()
    checks = []
    def add(name, ok, detail, required=True):
        checks.append({'name': name, 'ok': bool(ok), 'required': required, 'detail': detail})
    add('python', sys.version_info >= (3, 10), {'path': sys.executable, 'version': sys.version.split()[0]})
    versions = {}
    for name in ('ffmpeg', 'ffprobe'):
        try:
            executable = tool(name)
            version = run([executable, '-version'], timeout=15).stdout.splitlines()[0]
            match = re.search(r'version\s+(?:n)?(\d+)\.(\d+)', version)
            supported = match and (int(match[1]), int(match[2])) >= (6, 1)
            add(name, supported, {'path': executable, 'version': version, 'minimum': '6.1'})
            versions[name] = executable
        except PipelineError as exc:
            add(name, False, exc.as_dict())
    if 'ffmpeg' in versions:
        try:
            encoders = run([versions['ffmpeg'], '-hide_banner', '-encoders'], timeout=15).stdout
            filters = run([versions['ffmpeg'], '-hide_banner', '-filters'], timeout=15).stdout
            available_encoders = set(re.findall(r'^\s*[A-Z.]{6}\s+(\S+)', encoders, re.M))
            available_filters = set(re.findall(r'^\s*[A-Z.]{3}\s+(\S+)', filters, re.M))
            required_encoders = {'libx264', 'ffv1', 'aac', 'pcm_s16le', 'pcm_f32le', 'mjpeg'}
            required_filters = {'scale', 'crop', 'fps', 'concat', 'apad', 'amix', 'aresample', 'overlay', 'showinfo'}
            add('codecs', required_encoders <= available_encoders, {'missing': sorted(required_encoders - available_encoders)})
            add('filters', required_filters <= available_filters, {'missing': sorted(required_filters - available_filters)})
            for feature, names in [('titles', {'drawtext'}), ('burn_captions', {'subtitles'}),
                                   ('ducking', {'sidechaincompress'}), ('qa', {'loudnorm', 'blackdetect', 'silencedetect'})]:
                add(feature, names <= available_filters, {'missing': sorted(names - available_filters)}, required=False)
        except PipelineError as exc:
            add('capabilities', False, exc.as_dict())
    if config_path is not None:
        try:
            config = config_read(config_path)
            add('config', True, {'path': str(Path(config_path).resolve()), 'inbox_count': len(config['inbox_paths'])})
        except PipelineError as exc:
            add('config', False, exc.as_dict())
    existing = next((p for p in (root, *root.parents) if p.is_dir()), None)
    try:
        if existing is None:
            raise OSError('No existing parent directory')
        with tempfile.TemporaryFile(dir=existing):
            pass
        usage = shutil.disk_usage(existing)
        add('storage', usage.free >= 256 * 1024 * 1024, {'directory': str(existing), 'free_bytes': usage.free, 'writable': True})
    except OSError as exc:
        add('storage', False, {'message': str(exc), 'writable': False})
    for package in ('jsonschema', 'faster-whisper', 'google-genai', 'python-dotenv'):
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        add(package, installed is not None, {'version': installed, 'download_or_api_test_performed': False}, required=package == 'jsonschema')
    add('gemini_credential', bool(os.environ.get('GEMINI_API_KEY')), {'configured': bool(os.environ.get('GEMINI_API_KEY')), 'provider_test_performed': False}, required=False)
    for shell in ('powershell', 'pwsh'):
        path = shutil.which(shell)
        if path:
            try:
                version = run([path, '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'], timeout=15).stdout.strip()
                add(shell, True, {'path': path, 'version': version}, required=False)
            except PipelineError as exc:
                add(shell, False, exc.as_dict(), required=False)
        else:
            add(shell, False, 'Not installed; required only for the corresponding PowerShell entry point.', required=False)
    return {'version': 1, 'ready': all(c['ok'] for c in checks if c['required']), 'checks': checks}


def watch(root, config_path, once=False):
    from .jobs import ingest
    root = Path(root).resolve()
    config = config_read(config_path)
    state = root / 'state'
    state.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('video-pipeline-' + str(root))
    logger.setLevel(logging.INFO)
    (root / 'logs').mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / 'logs/watcher.log', maxBytes=1024 * 1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    health = {'version': 1, 'pid': os.getpid(), 'status': 'starting', 'last_success': None, 'error': None}
    try:
        with FileLock(state / 'watcher.lock'):
            stop = state / 'watcher-stop.request'
            stop.unlink(missing_ok=True)
            try:
                while not stop.is_file():
                    health.update(status='polling', heartbeat=utcnow(), stage='discover')
                    write_json(state / 'watcher-health.json', health)
                    for item in discover(config):
                        if not item['stable']:
                            continue
                        try:
                            health.update(stage='ingest', heartbeat=utcnow())
                            write_json(state / 'watcher-health.json', health)
                            row = ingest(root, item['path'], config, cancel=lambda: stop.is_file())
                            health.update(job_id=row['id'], stage=row['stage'], error=row['error'])
                            if row['status'] == 'ready':
                                health['last_success'] = row['prepared_at']
                            logger.info('job=%s status=%s stage=%s', row['id'], row['status'], row['stage'])
                        except PipelineError as exc:
                            health['error'] = exc.as_dict()
                            logger.warning('ingest error code=%s field=%s', exc.code, exc.field)
                    health.update(status='idle', heartbeat=utcnow())
                    write_json(state / 'watcher-health.json', health)
                    if once or stop.is_file():
                        return health
                    time.sleep(config['poll_seconds'])
            finally:
                health.update(status='stopped', heartbeat=utcnow())
                write_json(state / 'watcher-health.json', health)
    finally:
        logger.removeHandler(handler)
        handler.close()
