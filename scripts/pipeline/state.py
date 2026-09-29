"""Transactional local job registry; independent writers never share snapshots."""
import json
from contextlib import contextmanager
import sqlite3
import uuid
from pathlib import Path
from .common import FileLock, PipelineError, read_json, utcnow, digest, file_hash


class JobStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.state = self.root / 'state'
        self.state.mkdir(parents=True, exist_ok=True)
        self.path = self.state / 'jobs.sqlite3'
        with FileLock(self.state / 'schema.lock', timeout=30):
            with self.connect() as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE,
                    original_path TEXT, job_path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    status TEXT NOT NULL, stage TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    retry_at REAL NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    error TEXT, prepared_at TEXT)''')
                db.execute('CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(status, prepared_at)')
                db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                if not db.execute("SELECT 1 FROM metadata WHERE key='legacy_registry_imported'").fetchone():
                    self._import_legacy(db)
                    db.execute("INSERT INTO metadata VALUES ('legacy_registry_imported', '1')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=30000')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _import_legacy(self, db):
        registry = self.state / 'processed.json'
        if not registry.exists():
            return
        entries = read_json(registry)
        entries = entries if isinstance(entries, list) else [entries]
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('job_path'):
                continue
            job = Path(entry['job_path']).resolve()
            original = entry.get('original_path')
            now = entry.get('ingested_at') or utcnow()
            manifest = read_json(job / 'manifest.json') if (job / 'manifest.json').exists() else {}
            key = digest({'legacy_job': str(job)})
            expected = manifest.get('sha256')
            if original and Path(original).is_file() and expected:
                from .jobs import source_identity
                current = Path(original)
                candidate = source_identity(current)[0]
                # A reused pathname is not historical identity. Only a stable
                # full-hash match can claim today's source key; duplicate old
                # jobs retain separate historical keys instead of disappearing.
                if (file_hash(current).lower() == expected.lower()
                        and source_identity(current)[0] == candidate
                        and not db.execute('SELECT 1 FROM jobs WHERE source_key=?', (candidate,)).fetchone()):
                    key = candidate
            identifier = manifest.get('job_id', job.name)
            if db.execute('SELECT 1 FROM jobs WHERE id=?', (identifier,)).fetchone():
                identifier = digest({'legacy_job_id': str(job)})
            db.execute('''INSERT OR IGNORE INTO jobs
                (id,source_key,original_path,job_path,created_at,updated_at,status,stage,prepared_at)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (identifier, key, original, str(job), manifest.get('created_at', now),
                 now, 'ready' if (job / 'READY.txt').is_file() else 'failed', 'legacy-import', now))

    def reserve(self, key, original, job=None):
        now = utcnow()
        job_id = uuid.uuid4().hex
        job = Path(job).resolve() if job else self.root / 'jobs' / job_id
        with self.connect() as db:
            db.execute('''INSERT OR IGNORE INTO jobs
                (id,source_key,original_path,job_path,created_at,updated_at,status,stage)
                VALUES (?,?,?,?,?,?,'pending','allocated')''',
                (job_id, key, str(original) if original else None, str(job), now, now))
            row = db.execute('SELECT * FROM jobs WHERE source_key=? OR job_path=?', (key, str(job))).fetchone()
        return self.decode(row)

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        if result['error']:
            result['error'] = json.loads(result['error'])
        return result

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? OR job_path=?', (str(identifier), str(Path(identifier).resolve()))).fetchone()
        if row is None:
            raise PipelineError('unknown_job', 'job', f'Job not found: {identifier}', 'Use jobs-list to obtain a stable job ID.')
        return self.decode(row)

    def by_source(self, key):
        with self.connect() as db:
            return self.decode(db.execute('SELECT * FROM jobs WHERE source_key=?', (key,)).fetchone())

    def update(self, identifier, **fields):
        allowed = {'status', 'stage', 'attempts', 'retry_at', 'cancel_requested', 'error', 'prepared_at'}
        if not fields.keys() <= allowed:
            raise ValueError('Invalid state field')
        fields['updated_at'] = utcnow()
        if 'error' in fields and fields['error'] is not None:
            fields['error'] = json.dumps(fields['error'])
        with self.connect() as db:
            db.execute('UPDATE jobs SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', [*fields.values(), identifier])
        return self.get(identifier)

    def list(self, status=None, limit=100, offset=0):
        if not 1 <= limit <= 1000 or offset < 0:
            raise PipelineError('pagination', 'limit', 'Use limit 1..1000 and nonnegative offset.')
        with self.connect() as db:
            sql = 'SELECT * FROM jobs' + (' WHERE status=?' if status else '') + ' ORDER BY created_at DESC,id LIMIT ? OFFSET ?'
            rows = db.execute(sql, ([status] if status else []) + [limit, offset]).fetchall()
        return [self.decode(row) for row in rows]

    @staticmethod
    def prepared_artifacts(row):
        job = Path(row['job_path'])
        if not all((job / name).is_file() for name in ('READY.txt', 'manifest.json', 'analysis/probe.json')):
            return False
        try:
            manifest = read_json(job / 'manifest.json')
            info = read_json(job / 'analysis/probe.json')
            clone = (job / manifest['clone_path']).resolve() if manifest.get('clone_path') else None
            if clone is None or not clone.is_file() or not clone.is_relative_to((job / 'source').resolve()):
                return False
            if manifest.get('version', 1) >= 2:
                kinds = {stream['codec_type'] for stream in info['streams']}
                if not kinds or manifest.get('preparation_status') != 'complete':
                    return False
                if 'audio' in kinds and not (job / 'analysis/voiceover.wav').is_file():
                    return False
                if 'video' in kinds and not all((job / name).is_file() for name in ('edit/timeline.json', 'analysis/contact-sheet.jpg', 'analysis/samples/index.json')):
                    return False
            return True
        except (PipelineError, KeyError, TypeError, ValueError):
            return False

    def latest_ready(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs WHERE status='ready' ORDER BY prepared_at DESC,id").fetchall()
        for row in rows:
            record = self.decode(row)
            job = Path(record['job_path'])
            if self.prepared_artifacts(record):
                return record
            self.update(record['id'], status='stale', stage='missing-artifact',
                error={'code': 'missing_artifact', 'message': 'Prepared job artifacts are missing; explicitly retry/resume.'})
        raise PipelineError('no_ready_job', 'jobs', 'No prepared job is currently available.')

    def request_cancel(self, identifier):
        row = self.get(identifier)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone()
            active = current['status'] == 'processing'
            db.execute('UPDATE jobs SET cancel_requested=1,status=?,updated_at=? WHERE id=?',
                ('cancel_requested' if active else 'cancelled', utcnow(), row['id']))
            (Path(row['job_path']) / 'READY.txt').unlink(missing_ok=True)
        return self.get(row['id'])

    def finish_ready(self, identifier, prepared_at):
        from .common import atomic_write
        from .media import Cancelled
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone()
            if row['cancel_requested']:
                raise Cancelled()
            marker = Path(row['job_path']) / 'READY.txt'
            atomic_write(marker, ('READY\nJob: ' + identifier + '\nPrepared: ' + prepared_at + '\n').encode())
            db.execute("UPDATE jobs SET status='ready',stage='prepared',prepared_at=?,updated_at=?,error=NULL WHERE id=?",
                (prepared_at, utcnow(), identifier))
        return self.get(identifier)
