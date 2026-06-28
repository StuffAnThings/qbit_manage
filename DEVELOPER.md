# Developer Guide — Release & CI Reference

This document is for maintainers and contributors who need to understand the
release flow, versioning scheme, CI gates, and secrets hygiene for qBit Manage.

---

## Release Flow

Releases follow a three-step process involving two actors: CI automation and
the operator (a repository maintainer).

### Step 1 — Open a Release PR (CI, manual trigger)

Trigger the **Release PR** workflow from the GitHub Actions UI:

1. Go to **Actions → Release PR → Run workflow**.
2. Choose `version_bump_type` (patch / minor / major; default: patch).
3. Optionally supply `release_notes_override` to replace auto-generated notes.

The workflow:
- Checks out `develop`, reads `VERSION` (e.g. `4.7.2-develop5`), strips the
  `-developN` suffix, and computes the new release version per the bump type.
- **Creates a `release/v<NEW>` branch as a snapshot of develop** (so develop
  keeps moving while the release stabilizes — the release branch is a frozen
  copy at the snapshot point).
- Writes the new version to `VERSION` on the release branch and pushes it.
- Opens a PR from `release/v<NEW> → master` titled `Release v<NEW>`.
- PR body is auto-generated from `git log origin/master..HEAD --oneline --no-merges`,
  grouped by Conventional Commit prefix (`feat`, `fix`, `chore`, etc.).
- Builds the 5-platform binary + Tauri desktop bundle matrix via the reusable
  `build-binaries.yml` workflow.
- Creates a **draft** GitHub release tagged `v<NEW>` (`target_commitish`
  set to the release branch) with the auto-generated notes and built assets
  attached. The tag is **not pushed** yet — the draft is a testable preview.

> **Repo setting prerequisite:** enable **Settings → General → Pull Requests
> → Automatically delete head branches** so the `release/v<NEW>` branch is
> cleaned up on merge. If it's disabled, you'll need to delete the branch
> manually after merge.

### Step 2 — Operator Review and Merge

The operator:
1. Reviews the release PR, checks the draft release notes, and optionally downloads
   and tests the binaries attached to the draft GitHub release.
2. Verifies all CI checks are green on the PR.
3. Merges `release/v<NEW>` to `master`. **Use `Rebase and merge`** (not
   squash) so the individual Conventional Commit messages (`feat:`,
   `fix:`, etc.) survive on master. Rationale:
   - The project relies on Conventional Commit prefixes for change-log
     scanning (`git log --grep='^feat:'`) and for the release-notes
     auto-categorization above. Squashing collapses everything into one
     "Release v<X.Y.Z>" message and loses that signal.
   - `update-develop-branch.yml` resets `develop` to `master` after every
     release, so develop's history ends up matching master's. Rebase keeps
     that history granular and bisectable.
   - Individual commits remain revertible.
   - **Squash is hazardous:** a squash commit message is built from the PR
     title + the auto-generated changelog. If any line in it contains
     `[skip ci]` (VERSION-bump subjects historically did), GitHub skips
     **every** push-triggered workflow on master — no `tag.yml`, so no tag,
     no `version.yml`/`pypi`/develop-reset (this is exactly how the 4.9.0
     release silently no-op'd). `release-pr.yml` now strips bump subjects and
     neutralizes CI-skip tokens in the notes as a backstop, but **rebase-merge
     remains the supported path.**

   The release branch auto-deletes on merge (per the repo setting above).

### Step 3 — Post-Merge Automation (CI, auto-triggered on master push)

The master push triggers `tag.yml` (and `update-develop-branch.yml`) directly;
`tag.yml` then pushes the `v<X.Y.Z>` tag, which in turn triggers `version.yml`
and `pypi-publish.yml`. The cascade is two steps, not a single parallel burst:

| Workflow | What it does |
|----------|-------------|
| `tag.yml` | Reads `VERSION`, creates and pushes the `v<X.Y.Z>` tag via `Kometa-Team/tag-new-version`. |
| `pypi-publish.yml` | Triggered by the new `v*` tag; builds the Python package and publishes to PyPI via trusted publishing (OIDC, no API token needed). |
| `version.yml` | Triggered by the `v*` tag; builds + pushes the Docker image, then publishes the draft GitHub release that `release-pr.yml` already prepared — flips it from draft to published. Does **not** rebuild binaries. |
| `update-develop-branch.yml` | Resets `develop` to `master`, bumps `VERSION` to the next patch-develop1 (e.g. `4.7.3-develop1`), force-pushes develop, then triggers `develop.yml` to rebuild Docker develop images. |

After `tag.yml` pushes the `v<X.Y.Z>` tag, `version.yml` fires: it builds and
pushes the Docker image, then publishes the draft release (binaries and notes
were already attached by `release-pr.yml` in Step 1).

---

## Develop Builds & PR Artifacts

### Rolling develop pre-release

Every push to `develop` (excluding doc-only paths) triggers `develop.yml`, which:

1. Builds the full 5-platform binary + Tauri bundle matrix via `build-binaries.yml`.
2. Pushes the `:develop` Docker image.
3. Deletes and recreates the `latest-develop` rolling GitHub pre-release at the
   current develop HEAD (`gh release delete latest-develop --cleanup-tag`, then
   `gh release create latest-develop --prerelease --latest=false ...`).

The `latest-develop` tag is intentionally non-`v*` so it never triggers `tag.yml`,
`version.yml`, or `pypi-publish.yml`. Use it to grab a development binary without
waiting for a full release.

### PR cross-platform artifacts

By default, PRs do **not** run the 5-OS binary build — unlabeled PRs cost zero
runner minutes. When a maintainer adds the **`build` label** to a PR, `pr-build.yml`
triggers the full matrix via `build-binaries.yml` using the PR's head SHA. The
resulting `qbit-manage-release-assets` artifact is available for download from the
**Actions → PR Build Artifacts** workflow run, letting reviewers test all platforms
before merge. A concurrency group cancels superseded runs when new commits land on
the same labeled PR.

### Reusable build workflow (`build-binaries.yml`)

`build-binaries.yml` is a `workflow_call` reusable workflow — the single source of
truth for the PyInstaller + Tauri matrix. All three callers (`release-pr.yml`,
`develop.yml`, `pr-build.yml`) pass a `ref` input (branch / tag / SHA). The
workflow produces one consolidated `qbit-manage-release-assets` artifact containing
the 5 server binaries plus the per-platform desktop installer bundles.

---

## Hot-Fix Flow

For urgent fixes that cannot wait for the normal develop cycle:

1. Create a branch from `master` with the `hotfix/` prefix:
   ```bash
   git checkout master
   git pull origin master
   git checkout -b hotfix/fix-critical-crash
   ```
2. Make the minimal fix. Open a PR directly to `master`.
3. The PR requires explicit maintainer approval (branch protection rules apply).
4. Once merged, the same Step 3 automation fires (tag → pypi → version → develop reset).
5. The hot-fix commit is automatically backported to `develop` by
   `update-develop-branch.yml` (develop is reset to master after every master push).

> Never cherry-pick hot-fixes to develop manually — the reset workflow handles
> it, and manual cherry-picks create divergence.

---

## Versioning

Version strings live in a single file: `VERSION` at the repo root.

**Format:**

| Branch | Example | Meaning |
|--------|---------|---------|
| `develop` (active dev) | `4.7.2-develop5` | 5th auto-bump since 4.7.2 was cut |
| `master` (release) | `4.7.2` | Released version |

**Auto-bump mechanics:**

- The `bump-version-develop.yml` CI workflow (`scripts/pre-commit/increase_version.sh`
  is still present locally for optional manual use) auto-increments the `developN`
  counter on every push to `develop`. The pre-commit `increase-version` hook has been
  removed from `.pre-commit-config.yaml`; bumping is now CI-driven.
- After a master merge, `update-develop-branch.yml` sets the next version:
  it strips the release suffix, bumps the patch segment by 1, and appends
  `-develop1`. Example: `4.7.2` → `4.7.3-develop1`.

**Major/minor bumps** are handled by the Release PR workflow's `version_bump_type`
input — the workflow computes the new base version, writes it to the `release/v<NEW>`
branch, and opens the PR from that branch. `develop` is not modified during this step.

---

## CI Gates

Every PR to `develop` (and to `master`) is gated by `tests.yml` (triggered by
`pull_request` to master/main/develop), which runs pytest across Python
3.10–3.14. That is the only CI job that must pass before merge.

Ruff (lint/format) and yamllint are enforced as local pre-commit hooks, not as
CI jobs. `develop.yml` is a post-merge workflow triggered by
`push: branches:[develop]` — it is not a PR gate.

Branch protection on `master` requires at least one maintainer approval and all
status checks green.

---

## Secrets Hygiene

### check_no_tracker_secrets (pre-commit)

A local pre-commit hook (`check_no_tracker_secrets.py`)
will scan staged files for patterns that match tracker credentials (API keys,
passkeys, announce URLs with embedded tokens). The hook blocks commits that
would accidentally include live tracker credentials sourced from a local
`config/config.yml`.

**If the hook fires:**
1. Remove or redact the credential from the staged file.
2. Add the file to `.gitignore` if it should never be committed (e.g. a
   personal config snippet).
3. If this is a false positive, contact a maintainer — do not bypass with
   `--no-verify` without explicit approval.

### Workflow secrets

| Secret | Used by | Purpose |
|--------|---------|---------|
| `PAT` | `tag.yml`, `update-develop-branch.yml`, `version.yml`, `release-pr.yml` | Push tags, force-push develop, publish releases, and open release PRs (bypasses branch protection) |
| `GITHUB_TOKEN` | Most workflows | Default Actions token for read operations and PR creation |
| PyPI OIDC | `pypi-publish.yml` | Trusted publishing — no stored API token |

Secrets are managed in the repository's **Settings → Secrets and variables →
Actions**. Never hardcode tokens in workflow files.

---

## Troubleshooting

**Release PR workflow fails on version parse:**
The workflow expects `VERSION` to match `X.Y.Z-developN` on the `develop`
branch. If `VERSION` was manually edited to an unexpected format, correct it
before re-triggering.

**`update-develop-branch.yml` fails to force-push develop:**
This workflow requires the `PAT` secret (a personal access token with `repo`
scope and admin bypass for branch protection). Verify the secret is set and
has not expired.

**tag.yml creates the wrong tag:**
`Kometa-Team/tag-new-version` reads `VERSION` verbatim. If the version on
`master` contains a `-develop` suffix (it should not after a proper release
merge), the tag will be wrong. Fix `VERSION` on master and re-run the workflow.

**PyPI publish fails with 400 Conflict:**
A release with the same version was already uploaded. Increment the version
(patch bump) and issue a corrective release. PyPI does not allow re-uploading
the same version.

**`bump-version-develop.yml` triggers unexpectedly:**
This workflow runs on every push to `develop`. To prevent it from bumping
`VERSION` on a specific push, include `[skip-version-bump]` in the commit
message (the bump commit itself uses this). **Do not use `[skip ci]`** — it
gets replayed into release notes and, on a squash-merge, into the master commit
message, which skips the entire release chain.

**Release didn't run after a merge to master (no tag / no PyPI / no Docker):**
The master commit message contained a CI-skip token (`[skip ci]` etc.), so
GitHub skipped `tag.yml`. Confirm with `git log origin/master -1 --format=%B`.
Recover:
- `gh release edit v<X.Y.Z> --draft=false --latest` — publish the draft that
  `release-pr.yml` already built (binaries + notes attached).
- `gh workflow run tag.yml` and `gh workflow run update-develop-branch.yml` —
  manual `workflow_dispatch` levers to re-create the tag and reset develop.
- `gh workflow run pypi-publish.yml --ref master` — re-publish to PyPI.
Prevention: rebase-merge release PRs; never put `[skip ci]` in a commit that
can reach master.
