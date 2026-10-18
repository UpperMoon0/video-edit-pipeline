"""Reusable workspace contracts, real HTTP serving and synthetic range rendering."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'examples')]
from generate_fixtures import generate
from pipeline.common import PipelineError, read_json
from pipeline.workspace import Workspace, WORKSPACE_SCHEMA, handler, initialize, validate_project


class WorkspaceContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pipeline-workspace-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'source.mp4').write_bytes(b'synthetic media placeholder')
        self.timeline = self.root / 'timeline.json'
        self.timeline.write_text(json.dumps({'clips': [{'id': 'opening', 'source': 'source.mp4', 'duration': 2}],
                                             'output': 'output.mp4'}), encoding='utf-8')
        self.script = self.root / 'script.txt'
        self.script.write_text('A complete script.\n\nChào thế giới.\nFinal line.', encoding='utf-8-sig')
        self.manifest = initialize(self.timeline, self.root / 'review', script=self.script, title='Synthetic project')['project']

    def open(self, path=None):
        workspace = Workspace(path or self.manifest)
        self.addCleanup(workspace.close)
        return workspace

    def server(self, workspace):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(workspace))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown(); server.server_close(); thread.join(5)
        self.addCleanup(close)
        return f'http://127.0.0.1:{server.server_port}'

    def request(self, base, path, *, method='GET', headers=None, data=None):
        if data is not None:
            data = json.dumps(data).encode()
        request = urllib.request.Request(base + path, method=method, headers=headers or {}, data=data)
        try:
            return urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            return error

    def test_schema_and_new_project_creation_are_reusable(self):
        self.assertEqual(read_json(ROOT / 'schemas/workspace-v1.schema.json'), WORKSPACE_SCHEMA)
        first = self.open()
        second = self.open(initialize(self.timeline, self.root / 'another-review', title='Another project')['project'])
        self.assertEqual(first.public_project()['title'], 'Synthetic project')
        self.assertEqual(second.public_project()['title'], 'Another project')
        self.assertNotEqual(first.public_project()['workspace_id'], second.public_project()['workspace_id'])
        self.assertFalse(second.public_project()['has_script'])
        self.assertEqual(second.public_project()['storyboard'], [])
        self.assertIsNone(second.public_project()['master'])
        with self.assertRaises(FileExistsError):
            initialize(self.timeline, self.root / 'review')

    def test_initializer_uses_rational_frames_and_narration_without_render(self):
        self.timeline.write_text(json.dumps({'video': {'fps': '30000/1001'}, 'clips': [
            {'source': 'source.mp4', 'duration': .05}, {'source': 'source.mp4', 'duration': .1}], 'output': 'output.mp4'}))
        narration = self.root / 'narration.json'
        narration.write_text(json.dumps(['Opening', 'Ending']))
        with patch('pipeline.media.subprocess.Popen', side_effect=AssertionError('No render needed')):
            result = initialize(self.timeline, self.root / 'rational', narration=narration)
        project = self.open(result['project']).public_project()
        self.assertAlmostEqual(project['scenes'][1]['start'], 1001 / 30000)
        self.assertAlmostEqual(project['duration'], 4 * 1001 / 30000)
        self.assertEqual([s['text'] for s in project['scenes']], ['Opening', 'Ending'])
        narration.write_text('["wrong count"]')
        with self.assertRaises(ValueError):
            initialize(self.timeline, self.root / 'bad-narration', narration=narration)
        self.assertFalse((self.root / 'bad-narration').exists())

    def test_relative_paths_and_manifest_validation(self):
        project = read_json(self.manifest)
        project.update(media_root='..', timeline='../timeline.json', script='../script.txt')
        project['assets'] = {'asset-0': '../source.mp4'}
        Path(self.manifest).write_text(json.dumps(project))
        self.assertTrue(self.open().script.is_file())
        invalids = []
        for field, value in [('version', 2), ('duration', float('nan')), ('unexpected', 'field'), ('master', '/media/nope')]:
            bad = copy.deepcopy(project); bad[field] = value; invalids.append(bad)
        bad = copy.deepcopy(project); bad['scenes'][0]['duration'] = 1; invalids.append(bad)
        for bad in invalids:
            with self.subTest(bad=bad), self.assertRaises((ValueError, PipelineError)):
                validate_project(bad)
        project['assets']['asset-0'] = '../../outside.mp4'
        Path(self.manifest).write_text(json.dumps(project))
        with self.assertRaises(ValueError):
            self.open()

    def test_http_static_full_script_range_and_private_path_boundaries(self):
        workspace = self.open(); base = self.server(workspace)
        for path, mime in [('/', 'text/html'), ('/app.js', 'text/javascript'), ('/style.css', 'text/css')]:
            with self.request(base, path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(mime, response.headers['Content-Type'])
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        with self.request(base, '/api/script') as response:
            self.assertEqual(json.load(response)['text'], self.script.read_text(encoding='utf-8-sig'))
        self.script.write_text('Changed ending', encoding='utf-8')
        with self.request(base, '/api/script') as response:
            self.assertEqual(json.load(response)['text'], 'Changed ending')
        with self.request(base, '/api/project') as response:
            data = json.load(response)
            for private in ('assets', 'timeline', 'script', 'media_root'):
                self.assertNotIn(private, data)
        for headers in ({'Host': 'evil.invalid'}, {'Origin': 'https://evil.invalid'}):
            with self.request(base, '/api/script', headers=headers) as response:
                self.assertEqual(response.status, 403)
        for path in ('/project.json', '/timeline.json', '/media/../script.txt', '/api/tasks/unknown'):
            with self.request(base, path) as response:
                self.assertEqual(response.status, 404)
        with self.request(base, '/media/asset-0', headers={'Range': 'bytes=2-6'}) as response:
            self.assertEqual(response.status, 206); self.assertEqual(response.read(), b'nthet')
        with self.request(base, '/media/asset-0', method='HEAD') as response:
            self.assertEqual(response.status, 200); self.assertEqual(response.read(), b'')
        for value in ('bytes=-0', 'bytes=1000-', 'bytes=1-0', 'bytes=0-1,3-4'):
            with self.request(base, '/media/asset-0', headers={'Range': value}) as response:
                self.assertEqual(response.status, 416)
        empty = self.root / 'empty.mp4'; empty.touch(); workspace.assets['empty'] = empty
        with self.request(base, '/media/empty') as response:
            self.assertEqual(response.read(), b''); self.assertEqual(response.headers['Content-Length'], '0')

    def test_optional_script_storyboard_and_timeline(self):
        project = read_json(self.manifest)
        del project['script']; del project['timeline']
        project['storyboard'] = [dict(id='chapter', title='No footage yet', text='A draft.',
            start=0, duration=5, media=None, media_in=0)]
        Path(self.manifest).write_text(json.dumps(project))
        workspace = self.open(); base = self.server(workspace)
        self.assertFalse(workspace.public_project()['can_preview'])
        with self.request(base, '/api/script') as response:
            self.assertEqual(response.status, 404)
        with self.request(base, '/api/preview', method='POST', data={'start': 0, 'end': 1}) as response:
            self.assertEqual(response.status, 400)

    def test_preview_rejects_bad_ranges_and_serializes_tasks(self):
        workspace = self.open(); base = self.server(workspace)
        for start, end in [(True, 1), (0, float('nan')), (-1, 1), (0, 3), (1, 1), ('0', 1)]:
            with self.request(base, '/api/preview', method='POST', data={'start': start, 'end': end}) as response:
                self.assertEqual(response.status, 400)
        with patch.object(workspace.pool, 'submit') as submit:
            with self.request(base, '/api/preview', method='POST', data={'start': 0, 'end': 1}) as response:
                self.assertEqual(response.status, 202); key = json.load(response)['task']
            submit.assert_called_once()
            with self.assertRaises(ValueError):
                workspace.preview(0, 1)
            with self.request(base, '/api/tasks/' + key) as response:
                self.assertEqual(json.load(response)['status'], 'queued')

    def test_changed_asset_symlink_cannot_escape_media_root(self):
        outside = self.root.parent / (self.root.name + '-outside.txt')
        outside.write_text('private', encoding='utf-8'); self.addCleanup(outside.unlink)
        link = self.root / 'link.txt'
        try:
            link.symlink_to(self.script)
        except OSError:
            self.skipTest('Creating symlinks requires host support/Windows privileges')
        link.unlink()
        workspace = self.open(); base = self.server(workspace)
        self.script.unlink(); self.script.symlink_to(outside)
        with self.request(base, '/api/script') as response:
            self.assertEqual(response.status, 404)

    def test_shared_ui_is_allowlisted_without_project_data(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            subprocess.run(['git', 'init', '-q', str(directory)], check=True)
            (directory / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
            for path, ignored in [('scripts/pipeline/web/index.html', False), ('scripts/pipeline/web/app.js', False),
                                  ('scripts/pipeline/web/style.css', False), ('scripts/pipeline/web/project.json', True),
                                  ('jobs/private/edit/workspace/index.html', True), ('scripts/pipeline/web/script.txt', True)]:
                result = subprocess.run(['git', 'check-ignore', '-q', path], cwd=directory)
                self.assertEqual(result.returncode == 0, ignored, path)


class WorkspaceMedia(unittest.TestCase):
    def test_new_video_workspace_renders_and_serves_real_preview(self):
        with tempfile.TemporaryDirectory(prefix='workspace-media-') as directory:
            root = generate(Path(directory) / 'media')
            manifest = initialize(root / 'minimal.json', root / 'review', title='Synthetic preview')['project']
            workspace = Workspace(manifest)
            try:
                key = workspace.preview(.5, 1.5)
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    with workspace.lock:
                        task = copy.deepcopy(workspace.tasks[key])
                    if task['status'] in ('ready', 'failed'):
                        break
                    time.sleep(.1)
                self.assertEqual(task['status'], 'ready', task)
                self.assertTrue(workspace.assets[key].is_file())
                self.assertEqual(task['media'], '/media/' + key)
            finally:
                workspace.close()


if __name__ == '__main__':
    unittest.main()
