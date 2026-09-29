"""Actual Windows PowerShell 5.1 / PowerShell 7 process and scheduler contracts."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'examples')]
from generate_fixtures import generate
from pipeline.common import read_json, write_json, file_hash


@unittest.skipUnless(os.name == 'nt', 'Windows-specific contracts run in the Windows matrix and on a real Windows workstation.')
class PowerShellContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = [shutil.which('powershell'), shutil.which('pwsh')]
        if not all(cls.shells):
            raise RuntimeError('Windows test runs require BOTH Windows PowerShell 5.1 and PowerShell 7.')
        cls.temp = tempfile.TemporaryDirectory(prefix='pipeline-ps-')
        cls.root = Path(cls.temp.name)
        cls.media = generate(cls.root / 'media')

    @classmethod
    def tearDownClass(cls):
        for path in cls.root.rglob('*'):
            if path.is_file():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
        cls.temp.cleanup()

    def ps(self, shell, script, *arguments, timeout=90):
        return subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
            *map(str, arguments)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)

    def test_every_powershell_entrypoint_parses_on_both_shells(self):
        script = self.root / 'parse.ps1'
        script.write_text('param([string]$Scripts)\n$ErrorActionPreference="Stop"\nforeach ($file in Get-ChildItem -LiteralPath $Scripts -Filter *.ps1) { $tokens=$null; $errors=$null; [void][Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors); if ($errors.Count) { throw ($errors | Out-String) } }\n', encoding='utf-8-sig')
        for shell in self.shells:
            with self.subTest(shell=shell):
                result = self.ps(shell, script, ROOT / 'scripts')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_powershell_json_utf8_bom_nonascii_to_python(self):
        source = self.media / 'nguyên 日本語 clip.mkv'
        shutil.copyfile(self.media / 'red.mkv', source)
        script = self.root / 'bom.ps1'
        script.write_text('''param([string]$Python,[string]$Renderer,[string]$Source,[string]$Json,[string]$Output)
$ErrorActionPreference='Stop'
$spec=@{version=1;video=@{width=160;height=96;fps='30000/1001'};clips=@(@{source=$Source;duration=1});output=$Output;metadata=@{title='Chào Sunday 日本語'}}
$spec | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Json -Encoding UTF8
& $Python $Renderer $Json --validate
if ($LASTEXITCODE -ne 0) { throw 'Validation failed' }
''', encoding='utf-8-sig')
        for i, shell in enumerate(self.shells):
            with self.subTest(shell=shell):
                target = self.root / f'bom-{i}.json'
                output = self.root / f'never-created-{i}.mp4'
                result = self.ps(shell, script, '-Python', sys.executable, '-Renderer', ROOT / 'scripts/render_timeline.py',
                    '-Source', source, '-Json', target, '-Output', output)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(read_json(target)['metadata']['title'], 'Chào Sunday 日本語')
                self.assertEqual(read_json(target)['clips'][0]['source'], str(source))
                self.assertFalse(output.exists())
                if i == 0:
                    self.assertTrue(target.read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_sampler_uses_invariant_fractional_seek_on_both_shells(self):
        script = self.root / 'sample.ps1'
        script.write_text('''param([string]$Python,[string]$Sampler,[string]$Source,[string]$Output)
$ErrorActionPreference='Stop'
[Threading.Thread]::CurrentThread.CurrentCulture=[Globalization.CultureInfo]::GetCultureInfo('fr-FR')
& $Sampler -InputPath $Source -OutputDirectory $Output -IntervalSeconds 0.13 -StartSeconds 2.8 -EndSeconds 3 -Columns 2 -Rows 1 -ThumbnailWidth 160 -PythonPath $Python
''', encoding='utf-8-sig')
        for i, shell in enumerate(self.shells):
            with self.subTest(shell=shell):
                result = self.ps(shell, script, '-Python', sys.executable, '-Sampler', ROOT / 'scripts/Sample-Video.ps1',
                    '-Source', self.media / 'red.mkv', '-Output', self.root / f'samples-{i}')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                evidence = read_json(self.root / f'samples-{i}/index.json')
                self.assertTrue(all(2.8 <= frame['timestamp'] < 3 for frame in evidence['frames']))

    def test_ingest_resume_wrappers_on_both_shells(self):
        for i, shell in enumerate(self.shells):
            with self.subTest(shell=shell):
                workspace = self.root / f'workspace-{i}'
                config = workspace / 'config.json'
                write_json(config, {'inbox_paths': ['inbox'], 'extensions': ['.mkv'], 'stable_seconds': 0, 'contact_sheet_frames': 2})
                command = ['-Root', workspace, '-ConfigPath', config, '-PythonPath', sys.executable]
                result = self.ps(shell, ROOT / 'scripts/MediaPipeline.ps1', *command, '-Action', 'Ingest', '-SourcePath', self.media / 'red.mkv')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                row = json.loads(result.stdout)['result']
                self.assertEqual(row['status'], 'ready')
                original = read_json(Path(row['job_path']) / 'manifest.json')
                result = self.ps(shell, ROOT / 'scripts/MediaPipeline.ps1', *command, '-Action', 'Resume', '-JobPath', row['job_path'])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                resumed = read_json(Path(row['job_path']) / 'manifest.json')
                for key in ('original_path', 'sha256', 'created_at'):
                    self.assertEqual(original[key], resumed[key])
                self.assertFalse(Path(resumed['clone_path']).stat().st_mode & stat.S_IWUSR)

    @unittest.skipUnless(os.environ.get('PIPELINE_TEST_TASKS') == '1', 'Requires an interactive Windows account; enabled for isolated workstation acceptance, not hosted CI services.')
    def test_real_scheduled_task_install_start_status_stop_remove(self):
        workspace = self.root / 'task-workspace'
        inbox = workspace / 'inbox'
        inbox.mkdir(parents=True)
        shutil.copyfile(self.media / 'red.mkv', inbox / 'ready.mkv')
        config = workspace / 'config.json'
        write_json(config, {'inbox_paths': [str(inbox)], 'extensions': ['.mkv'], 'poll_seconds': .1,
            'stable_seconds': 0, 'contact_sheet_frames': 2})
        name = 'VideoEditPipeline-Test-' + uuid.uuid4().hex[:12]
        script = ROOT / 'scripts/Install-Watcher.ps1'
        args = ['-Root', workspace, '-ConfigPath', config, '-PythonPath', sys.executable, '-TaskName', name]
        shell = self.shells[0]
        try:
            result = self.ps(shell, script, *args, '-Action', 'Install', '-StartNow')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            deadline = time.monotonic() + 90
            health = None
            while time.monotonic() < deadline:
                path = workspace / 'state/watcher-health.json'
                if path.exists():
                    health = read_json(path)
                    if health.get('last_success'):
                        break
                time.sleep(.25)
            self.assertIsNotNone(health, 'Task did not start the foreground watcher')
            self.assertIsNotNone(health.get('last_success'), health)
            result = self.ps(shell, script, *args, '-Action', 'Status')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)['installed'])
            result = self.ps(shell, script, *args, '-Action', 'Stop')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'stop-requested', result.stdout)
            self.assertTrue((workspace / 'state/watcher-stop.request').is_file())
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                health = read_json(workspace / 'state/watcher-health.json')
                if health['status'] == 'stopped':
                    break
                time.sleep(.2)
            self.assertEqual(health['status'], 'stopped')
            result = self.ps(shell, script, *args, '-Action', 'Remove')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            status = self.ps(shell, script, *args, '-Action', 'Status')
            self.assertFalse(json.loads(status.stdout)['installed'])
        finally:
            self.ps(shell, script, *args, '-Action', 'Remove')


if __name__ == '__main__':
    unittest.main()
