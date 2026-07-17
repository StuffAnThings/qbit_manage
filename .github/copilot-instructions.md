# qBit Manage Copilot Instructions

## Repository and branch model

- Target normal pull requests to `develop`. Never target `master` except an explicitly approved `hotfix/*` branch.
- Branch from the current `develop` tip and keep changes focused on one issue or behavior.
- Use Conventional Commit syntax for commit messages and PR titles: `type(optional-scope): description`.
- Read `CLAUDE.md` for project rules, `docs/Contributing.md` for contributor workflow, and `DEVELOPER.md` before changing release automation.

## Implementation standards

- Support Python 3.10 and newer.
- Follow existing module patterns and prefer the smallest change that fixes the behavior.
- Validate input at API, CLI, configuration, and filesystem boundaries.
- Handle errors explicitly. Preserve the original failure context in logs and return clear user-facing API errors.
- Avoid mutating caller-owned objects. Return new values or copies when state must change.
- Keep functions focused, avoid deep nesting, and use descriptive names.
- Comments explain non-obvious constraints or rationale, not what the code already states.
- Never hardcode credentials, tracker passkeys, announce URLs, API keys, or other secrets.

## Python and tests

- Format and lint with Ruff using the repository configuration and 130-character line length.
- Add regression tests for bug fixes and tests for new behavior.
- Use the factories in `tests/factories.py` instead of directly constructing core classes that require qBittorrent state.
- Keep tests deterministic and independent of a live qBittorrent instance unless the test is explicitly an integration test.
- Run the narrowest relevant tests first, then the related suite.

```bash
ruff check .
ruff format --check .
pytest tests/
pre-commit run --all-files
```

## Web UI

- Preserve the existing vanilla HTML, CSS, and JavaScript architecture unless a change explicitly requires a new dependency.
- Maintain responsive behavior and verify layouts at the breakpoints documented in `web-ui/css/responsive.css`.
- Treat long torrent names, paths, tracker URLs, and log lines as expected input. They must not create horizontal page overflow.
- Preserve accessibility semantics, keyboard behavior, labels, focus states, and reduced-motion feature queries.

## API, configuration, and logging

- Keep FastAPI routes authenticated and rate-limited according to existing endpoint patterns.
- Resolve filesystem paths and verify containment before reading or writing user-selected files.
- Register configuration keys through the existing `check_for_attribute` patterns in `modules/config.py`.
- Preserve secret redaction in every logging format and avoid changes that corrupt line-delimited JSON output.
- Keep text-mode logging behavior compatible unless the requested change explicitly updates it.

## GitHub Actions and releases

- This is a public repository. Use GitHub-hosted runners and never execute public pull request code on private or self-hosted infrastructure.
- Pin third-party actions to full commit SHAs and retain the version comment.
- Use least-privilege job permissions.
- Do not suppress GitHub CLI or API errors when checking whether a release, tag, or artifact exists. Handle an explicit not-found response separately from authentication, rate-limit, or transient failures.
- Preserve the release flow documented in `DEVELOPER.md`: release PR draft, merge to `master`, version tag, production publication, then synchronization back to `develop`.
- Keep stable tags under `v*`; rolling develop tags must not trigger stable-release workflows.

## Review priorities

When reviewing changes, prioritize:

1. Data loss, unintended torrent deletion, and filesystem containment.
2. Authentication, secret exposure, unsafe API input, and permission expansion.
3. Release, versioning, and branch-flow regressions.
4. Behavior changes without regression tests.
5. Web UI overflow, accessibility, and desktop/mobile regressions.

Report concrete findings with the affected file and line. Do not invent failures when the change is correct.
