"""Shared JSON and atomic-file contracts for generated pipeline artifacts."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class PipelineError(Exception):
    def __init__(self, code, field, message, hint=''):
        super().__init__(message)
        self.code, self.field, self.message, self.hint = code, field, message, hint

    def as_dict(self):
        return dict(code=self.code, field=self.field, message=self.message, hint=self.hint)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON number: ' + value)))
    except (OSError, ValueError) as exc:
        raise PipelineError('invalid_json', str(path), str(exc), 'Provide valid UTF-8 JSON; BOM is accepted.') from exc


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def file_hash(path, cancel=None):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            if cancel is not None:
                from .media import check_cancel
                check_cancel(cancel)
            sha.update(block)
    return sha.hexdigest()


def resolve(base, value):
    return (Path(base) / value).resolve()


def same_file(a, b):
    a, b = Path(a), Path(b)
    if a.resolve() == b.resolve():
        return True
    try:
        return a.samefile(b)
    except OSError:
        return False


def reject_alias(output, inputs):
    for source in inputs:
        if same_file(output, source):
            raise PipelineError('input_output_alias', 'output', f'Output aliases input: {source}', 'Choose a distinct output file.')


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json_bytes(value))


class FileLock:
    """OS-held lock; process death releases ownership. Never unlink lock files."""
    def __init__(self, path, timeout=0):
        self.path, self.timeout, self.stream = Path(path), timeout, None

    def __enter__(self):
        import time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            self.stream.write(b'\0')
            self.stream.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError as exc:
                if time.monotonic() >= deadline:
                    self.stream.close()
                    raise PipelineError('busy', str(self.path), 'Another process owns this operation.', 'Retry after it completes; do not delete locks.') from exc
                time.sleep(.05)

    def __exit__(self, *args):
        try:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_UN)
        finally:
            self.stream.close()


@contextlib.contextmanager
def output_transaction(output, inputs=(), overwrite=True):
    output = Path(output)
    reject_alias(output, inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(output.with_name(f'.{output.name}.lock')):
        reject_alias(output, inputs)
        if output.exists() and not overwrite:
            raise PipelineError('output_exists', 'output', f'{output} already exists.')
        fd, name = tempfile.mkstemp(prefix=f'.{output.stem}.render-', suffix=output.suffix, dir=output.parent)
        os.close(fd)
        temp = Path(name)
        try:
            yield temp  # caller must finish validation before returning here
            if not temp.is_file() or not temp.stat().st_size:
                raise PipelineError('empty_output', 'output', 'No usable output was produced.')
            with temp.open('rb') as stream:
                os.fsync(stream.fileno())
            reject_alias(output, inputs)
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
