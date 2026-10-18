# Contributing

Start with `python -m pip install -r requirements.txt`, then run `python -m unittest discover -s tests -v` and `git diff --check`. Tests use synthetic media in owned temporary workspaces. FFmpeg is mandatory: media coverage must not be converted to an unconditional skip. Windows runs also require PowerShell 5.1 and 7. Never use personal footage, provider credentials, a private runner, or a paid/model-download call as an ordinary pull-request test dependency.

Keep timeline schema changes in `scripts/pipeline/schema.py` and regenerate `schemas/timeline-v1.schema.json`; their equality is tested. Unknown fields must fail rather than disappear silently. Preserve stable clip IDs and optimistic revision checks. Changes to cut rendering must invalidate incompatible cache entries. Public schema evolution is separate from application versioning (`pipeline.__version__`); breaking schema changes require a new version and migration instructions.

For every regression, include a test that would fail before the fix. Prefer decoded frame/audio assertions and source/output hashes over exit-code-only tests. Registry changes need concurrent-process, interruption, and retry tests. Publish an output only after validation, and never delete or overwrite files merely because their names look temporary.

Before committing, inspect `git status`, `git diff --cached`, and `git check-ignore` for generated/private paths. Do not widen `.gitignore` to publish jobs, recordings, transcripts, prompts, credentials, downloaded tools, or fonts. Newly needed source/documentation directories must be allowlisted narrowly.

This project uses the maintainer-selected MIT license in `LICENSE`. Do not copy third-party implementation code/assets without permission and attribution; the project license does not relicense third-party media, fonts, or dependencies.
