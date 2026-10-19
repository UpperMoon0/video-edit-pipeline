"""One canonical edit: HTTP, stale-render regressions and real composed previews."""
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
from pipeline.common import PipelineError, read_json, write_json, digest
from pipeline.timeline import load_timeline
from pipeline.workspace import Workspace, WORKSPACE_SCHEMA, handler, initialize, validate_project


class WorkspaceContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pipeline-workspace-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'source.mp4').write_bytes(b'synthetic media placeholder')
        self.timeline = self.root / 'timeline.json'
        write_json(self.timeline, {'clips': [{'id': 'opening', 'source': 'source.mp4', 'duration': 2}], 'output': 'output.mp4'})
        self.script = self.root / 'script.txt'
        self.script.write_text('A complete script.\n\nChào thế giới.\nFinal line.', encoding='utf-8-sig')
        self.manifest = initialize(self.timeline, self.root / 'review', script=self.script, title='Synthetic project')['project']

    def open(self, path=None):
        workspace = Workspace(path or self.manifest)
        self.addCleanup(workspace.close)
        return workspace

    def server(self, workspace):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(workspace))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def close():
            server.shutdown(); server.server_close(); thread.join(5)
        self.addCleanup(close)
        return f'http://127.0.0.1:{server.server_port}'

    def request(self, base, path, *, method='GET', headers=None, data=None):
        if data is not None: data = json.dumps(data).encode()
        request = urllib.request.Request(base + path, method=method, headers=headers or {}, data=data)
        try: return urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error: return error

    def test_schema_and_single_timeline_initialization(self):
        self.assertEqual(read_json(ROOT / 'schemas/workspace-v2.schema.json'), WORKSPACE_SCHEMA)
        project = read_json(self.manifest)
        self.assertEqual(set(project), {'version', 'title', 'media_root', 'timeline'})
        self.assertEqual(project['version'], 2)
        self.assertNotIn('storyboard', self.open().public_project())
        self.assertIn('Chào thế giới', load_timeline(self.timeline).spec['clips'][0]['editorial']['text'])
        with self.assertRaises(FileExistsError): initialize(self.timeline, self.root / 'review')
        # No second script can silently change what the timeline says.
        self.script.write_text('An unrelated later draft', encoding='utf-8')
        self.assertNotIn('unrelated', self.open().script_text())
        second = self.open(initialize(self.timeline, self.root / 'another')['project'])
        self.assertNotEqual(self.open().public_project()['workspace_id'], second.public_project()['workspace_id'])

    def test_rational_frame_grid_and_explicit_narration_mapping(self):
        write_json(self.timeline, {'video': {'fps': '30000/1001'}, 'clips': [
            {'source': 'source.mp4', 'duration': .05}, {'source': 'source.mp4', 'duration': .1}], 'output': 'output.mp4'})
        narration = self.root / 'narration.json'; write_json(narration, ['Opening', 'Ending'])
        with patch('pipeline.media.subprocess.Popen', side_effect=AssertionError('No render needed')):
            result = initialize(self.timeline, self.root / 'rational', narration=narration)
        project = self.open(result['project']).public_project()
        self.assertAlmostEqual(project['scenes'][1]['start'], 1001 / 30000)
        self.assertAlmostEqual(project['duration'], 4 * 1001 / 30000)
        self.assertEqual([s['text'] for s in project['scenes']], ['Opening', 'Ending'])
        for kwargs in ({'script': self.script}, {'narration': self.script}):
            with self.assertRaises((ValueError, PipelineError)): initialize(self.timeline, self.root / 'bad', **kwargs)
        self.assertFalse((self.root / 'bad').exists())

    def test_rejects_two_edits_and_unsafe_roots(self):
        for fields in ({'version': 1, 'storyboard': []}, {'storyboard': []}, {'scenes': []}, {'script': str(self.script)}, {'duration': 2}):
            bad = {**read_json(self.manifest), **fields}
            with self.subTest(fields=fields), self.assertRaises(ValueError): validate_project(bad)
        project = read_json(self.manifest); project.update(media_root='..', timeline='../timeline.json')
        write_json(self.manifest, project)
        self.assertEqual(self.open().public_project()['duration'], 2)
        outside = self.root.parent / (self.root.name + '-outside.json')
        write_json(outside, read_json(self.timeline)); self.addCleanup(outside.unlink)
        project['timeline'] = str(outside); write_json(self.manifest, project)
        with self.assertRaises(ValueError): self.open()

    def test_text_import_cannot_keep_older_recorded_speech_or_bind_its_export(self):
        spec = read_json(self.timeline)
        spec['clips'][0]['editorial']['narration_status'] = 'recorded'
        spec['clips'][0]['audio'] = {'mode': 'preserve'}
        (self.root / 'voice.wav').write_bytes(b'placeholder; initialization must not render')
        spec['audio'] = {'voiceover': 'voice.wav', 'ducking': {'enabled': True}}
        write_json(self.timeline, spec)
        self.script.write_text('Replacement words', encoding='utf-8')
        with self.assertRaises(ValueError):
            initialize(self.timeline, self.root / 'wrong-master', script=self.script, master=self.root / 'source.mp4')
        self.assertEqual(read_json(self.timeline), spec)
        initialize(self.timeline, self.root / 'new-text', script=self.script)
        updated = read_json(self.timeline)
        self.assertNotIn('voiceover', updated['audio']); self.assertNotIn('ducking', updated['audio'])
        self.assertEqual(updated['clips'][0]['audio']['mode'], 'mute')
        self.assertEqual(updated['clips'][0]['editorial']['narration_status'], 'pending')

    def test_changed_timeline_refreshes_script_scene_times_and_invalidates_master(self):
        manifest = initialize(self.timeline, self.root / 'with-export', master=self.root / 'source.mp4')['project']
        workspace = self.open(manifest)
        self.assertIsNotNone(workspace.public_project()['master'])
        spec = read_json(self.timeline)
        spec['clips'][0]['editorial']['text'] = 'The new opening.'
        spec['clips'][0]['duration'] = 1
        # Hash binding protects even an external writer that forgot to bump revision.
        write_json(self.timeline, spec)
        public = workspace.public_project()
        self.assertIsNone(public['master']); self.assertTrue(public['render_stale'])
        self.assertEqual(public['duration'], 1)
        self.assertIn('The new opening.', workspace.script_text())

    def test_rebound_export_at_same_path_gets_a_new_playback_url(self):
        manifest = initialize(self.timeline, self.root / 'reused-export', master=self.root / 'source.mp4')['project']
        workspace = self.open(manifest); before = workspace.public_project()
        spec = read_json(self.timeline); spec['revision'] += 1
        spec['clips'][0]['editorial']['notes'] = 'Replaced illustration picture'
        write_json(self.timeline, spec)
        # Simulate delivery rebinding a newly composed export at the same path.
        workspace.project['render']['timeline_sha256'] = digest(workspace.current().spec)
        after = workspace.public_project()
        self.assertNotEqual(before['master'], after['master'])
        self.assertEqual(before['master'].split('?')[0], after['master'].split('?')[0])
        base = self.server(workspace)
        with self.request(base, after['master'], headers={'Range': 'bytes=2-6'}) as response:
            self.assertEqual(response.status, 206); self.assertEqual(response.read(), b'nthet')

    def test_http_shared_ui_script_ranges_and_boundaries(self):
        workspace = self.open(); base = self.server(workspace)
        for path, mime in [('/', 'text/html'), ('/app.js', 'text/javascript'), ('/style.css', 'text/css')]:
            with self.request(base, path) as response:
                self.assertEqual(response.status, 200); self.assertIn(mime, response.headers['Content-Type'])
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        with self.request(base, '/') as response:
            html = response.read().decode()
            self.assertNotIn('Revised storyboard', html); self.assertNotIn('Existing cut', html)
        with self.request(base, '/api/script') as response:
            self.assertEqual(json.load(response)['text'], workspace.script_text())
        with self.request(base, '/api/project') as response:
            data = json.load(response)
            for private in ('assets', 'timeline', 'script', 'media_root'): self.assertNotIn(private, data)
        for path in ('/project.json', '/timeline.json', '/media/../script.txt', '/api/tasks/unknown'):
            with self.request(base, path) as response: self.assertEqual(response.status, 404)
        for headers in ({'Host': 'evil.invalid'}, {'Origin': 'https://evil.invalid'}):
            for path in ('/api/script', '/api/edit'):
                with self.request(base, path, headers=headers) as response: self.assertEqual(response.status, 403)
        media = data['scenes'][0]['media']
        with self.request(base, media, headers={'Range': 'bytes=2-6'}) as response:
            self.assertEqual(response.status, 206); self.assertEqual(response.read(), b'nthet')
        with self.request(base, media, method='HEAD') as response: self.assertEqual(response.read(), b'')
        for value in ('bytes=-0', 'bytes=1000-', 'bytes=1-0', 'bytes=0-1,3-4'):
            with self.request(base, media, headers={'Range': value}) as response: self.assertEqual(response.status, 416)

    def test_preview_requires_current_edit_and_freezes_snapshot(self):
        workspace = self.open(); base = self.server(workspace); fingerprint = workspace.public_project()['timeline_sha256']
        for start, end in [(True, 1), (0, float('nan')), (-1, 1), (0, 3), (1, 1), ('0', 1)]:
            with self.request(base, '/api/preview', method='POST', data={'start': start, 'end': end, 'timeline_sha256': fingerprint}) as response:
                self.assertEqual(response.status, 400)
        with self.assertRaises(ValueError): workspace.preview(0, 1, 'outdated')
        with patch.object(workspace.pool, 'submit') as submit:
            key = workspace.preview(0, 1, fingerprint)
            snapshot = submit.call_args.args[-1]
            self.assertEqual(read_json(snapshot)['clips'][0]['source'], str(self.root / 'source.mp4'))
            spec = read_json(self.timeline); spec['clips'][0]['editorial']['text'] = 'Later edit'; write_json(self.timeline, spec)
            self.assertNotEqual(digest(workspace.current().spec), workspace.tasks[key]['timeline_sha256'])
            self.assertNotIn('Later edit', json.dumps(read_json(snapshot)))
            with self.assertRaises(ValueError): workspace.preview(0, 1, workspace.public_project()['timeline_sha256'])

    def test_changed_asset_symlink_cannot_escape_root(self):
        outside = self.root.parent / (self.root.name + '-outside.txt'); outside.write_text('private'); self.addCleanup(outside.unlink)
        workspace = self.open(); base = self.server(workspace); media = workspace.public_project()['scenes'][0]['media']
        try:
            link = self.root / 'link.txt'; link.symlink_to(outside); link.unlink()
        except OSError: self.skipTest('Symlinks require host permission')
        (self.root / 'source.mp4').unlink(); (self.root / 'source.mp4').symlink_to(outside)
        with self.request(base, media) as response: self.assertEqual(response.status, 404)

    def test_shared_ui_is_allowlisted_without_private_project(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory); subprocess.run(['git', 'init', '-q', str(directory)], check=True)
            (directory / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
            for path, ignored in [('scripts/pipeline/web/index.html', False), ('scripts/pipeline/web/app.js', False),
                                  ('scripts/pipeline/web/project.json', True), ('jobs/private/edit/workspace/project.json', True)]:
                result = subprocess.run(['git', 'check-ignore', '-q', path], cwd=directory)
                self.assertEqual(result.returncode == 0, ignored)


class WorkspaceMedia(unittest.TestCase):
    def test_edit_script_trim_reorder_undo_and_compose_same_timeline(self):
        with tempfile.TemporaryDirectory(prefix='workspace-media-') as directory:
            root = generate(Path(directory) / 'media')
            timeline_path = root / 'minimal.json'
            spec = read_json(timeline_path); spec['audio'] = {}; write_json(timeline_path, spec)
            manifest = initialize(timeline_path, root / 'review')['project']
            workspace = Workspace(manifest)
            try:
                public = workspace.public_project(); first = public['scenes'][0]['id']; revision = public['revision']
                public = workspace.edit(revision, {'op': 'editorial', 'clip_id': first,
                    'fields': {'text': 'New opening.', 'title': 'Start here'}})
                self.assertEqual(public['scenes'][0]['text'], 'New opening.')
                self.assertIn('New opening.', workspace.script_text())
                self.assertEqual(public['scenes'][0]['narration_status'], 'pending')
                with self.assertRaises(PipelineError) as error:
                    workspace.edit(revision, {'op': 'editorial', 'clip_id': first, 'fields': {'text': 'Stale'}})
                self.assertEqual(error.exception.code, 'stale_revision')
                before = timeline_path.read_bytes()
                with self.assertRaises(PipelineError):
                    workspace.edit(public['revision'], {'op': 'editorial', 'clip_id': first, 'fields': {'source': '/private'}})
                self.assertEqual(before, timeline_path.read_bytes())
                public = workspace.edit(public['revision'], {'op': 'trim', 'clip_id': first, 'in': .1, 'duration': 1, 'ripple': True})
                self.assertEqual(public['scenes'][0]['duration'], 1)
                if len(public['scenes']) > 1:
                    order = [s['id'] for s in public['scenes']][::-1]
                    public = workspace.edit(public['revision'], {'op': 'reorder', 'clip_ids': order})
                    self.assertEqual([s['id'] for s in public['scenes']], order)
                public = workspace.edit(public['revision'], {'op': 'undo', 'revision': revision})
                self.assertNotIn('New opening.', workspace.script_text())
                key = workspace.preview(.5, 1.5, public['timeline_sha256'])
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    with workspace.lock: task = copy.deepcopy(workspace.tasks[key])
                    if task['status'] in ('ready', 'failed'): break
                    time.sleep(.1)
                self.assertEqual(task['status'], 'ready', task)
                self.assertEqual(task['timeline_sha256'], public['timeline_sha256'])
                self.assertTrue(workspace.assets[task['media'][7:]].is_file())
            finally: workspace.close()

    def test_http_edits_invalidate_recorded_voice_and_reject_stale_writes(self):
        with tempfile.TemporaryDirectory(prefix='workspace-edit-http-') as directory:
            root = generate(Path(directory) / 'media')
            path = root / 'minimal.json'
            spec = read_json(path)
            spec['clips'][0].update(audio={'mode': 'preserve'}, editorial={'text': 'Old words', 'narration_status': 'recorded'})
            write_json(path, spec)
            workspace = Workspace(initialize(path, root / 'review')['project'])
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(workspace))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            def post(body):
                req = urllib.request.Request(base + '/api/edit', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
                try: return urllib.request.urlopen(req)
                except urllib.error.HTTPError as error: return error
            try:
                public = workspace.public_project(); revision = public['revision']; first = public['scenes'][0]['id']
                with post({'expected_revision': revision, 'operation': {'op': 'editorial', 'clip_id': first, 'fields': {'title': 'New title'}}}) as response:
                    self.assertEqual(response.status, 200); public = json.load(response)
                self.assertIn('voiceover', read_json(path)['audio'])
                with self.assertRaises(ValueError):
                    workspace.edit(public['revision'], {'op': 'reorder', 'clip_ids': [s['id'] for s in public['scenes']][::-1]})
                with post({'expected_revision': public['revision'], 'operation': {'op': 'editorial', 'clip_id': first, 'fields': {'text': 'New words'}}}) as response:
                    self.assertEqual(response.status, 200); public = json.load(response)
                self.assertNotIn('voiceover', read_json(path)['audio'])
                self.assertEqual(public['scenes'][0]['audio_mode'], 'mute')
                self.assertEqual(public['scenes'][0]['narration_status'], 'pending')
                with post({'expected_revision': revision, 'operation': {'op': 'editorial', 'clip_id': first, 'fields': {'text': 'Stale'}}}) as response:
                    self.assertEqual(response.status, 409)
                self.assertEqual(workspace.public_project()['scenes'][0]['text'], 'New words')
            finally:
                server.shutdown(); server.server_close(); thread.join(5); workspace.close()


if __name__ == '__main__': unittest.main()
