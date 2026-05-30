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
- PR body is auto-generated from `git log master..release/v<NEW> --oneline`,
  grouped by Conventional Commit prefix (`feat`, `fix`, `chore`, etc.).
- Creates a **draft** GitHub release tagged `v<NEW>` (`target_commitish`
  set to the release branch) with the same notes. The tag is **not pushed**
  yet — the draft exists only as a preview.

> **Repo setting prerequisite:** enable **Settings → General → Pull Requests
> → Automatically delete head branches** so the `release/v<NEW>` branch is
> cleaned up on merge. If it's disabled, you'll need to delete the branch
> manually after merge.

### Step 2 — Operator Review and Merge

The operator:
1. Reviews the release PR and checks the draft release notes.
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

   The release branch auto-deletes on merge (per the repo setting above).

### Step 3 — Post-Merge Automation (CI, auto-triggered on master push)

Four workflows fire in parallel after the master push:

| Workflow | What it does |
|----------|-------------|
| `tag.yml` | Reads `VERSION`, creates and pushes the `v<X.Y.Z>` tag via `Kometa-Team/tag-new-version`. |
| `pypi-publish.yml` | Triggered by the new `v*` tag; builds the Python package and publishes to PyPI via trusted publishing (OIDC, no API token needed). |
| `version.yml` | Builds standalone PyInstaller binaries (Linux amd64/arm64, Windows, macOS) and the Tauri desktop bundles; attaches them to the GitHub release. |
| `update-develop-branch.yml` | Resets `develop` to `master`, bumps `VERSION` to the next patch-develop1 (e.g. `4.7.3-develop1`), force-pushes develop, then triggers `develop.yml` to rebuild Docker develop images. |

The draft release created in Step 1 is promoted to published once `tag.yml`
pushes the matching tag.

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

Every PR to `develop` runs the `develop.yml` workflow, which includes:

- **Ruff** — lint and format check (non-zero exit blocks merge)
- **yamllint** — strict YAML validation for any changed YAML files
- **pytest** — full test suite (~168 tests)
- **Docker build** — multi-arch image build (amd64, arm64, arm/v7) to catch
  import and dependency errors before release

The Release PR to `master` must also pass these same checks. Branch protection
on `master` requires at least one maintainer approval and all status checks
green.

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
| `PAT` | `tag.yml`, `update-develop-branch.yml` | Push tags and force-push develop (bypasses branch protection) |
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
This workflow runs on every push to `develop`. If you need to prevent it from
bumping `VERSION` on a specific push, include `[skip ci]` in the commit message
or use the `paths-ignore` exemptions already in the workflow.
