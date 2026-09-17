# SKIF GitHub Deployment Implementation Plan

> **For agentic workers:** Execute the approved plan in this session. Independent host bootstrap work may use subagent-driven-development; deployment and application readiness share state and are implemented sequentially. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Deliver a tested GitHub-to-VM deployment package and the shortest accurate remaining owner setup.

**Architecture:** GitHub-hosted CI validates source; a repository-scoped self-hosted runner deploys one immutable Docker image at a time. Configuration and runtime persist outside releases; a failed candidate rolls back to the previous image.

**Tech Stack:** Python 3.12 standard library, Docker, GitHub Actions, Ubuntu 24.04.

**Spec:** `docs/superpowers/specs/2026-09-17-github-deployment.md`

## Global Constraints

- Owner amendment dated 2026-09-17: reuse existing `jukovskayasv-alt/rastem_vmeste`; it is currently public and must be made private before any self-hosted runner is installed.
- Production source is the repository-root application on dedicated branch `skif`; existing `main` and the website remain unchanged.
- Deployment target: existing VM only; no new paid resources.
- No real secrets, getUpdates, AI charges or Telegram sends during local tests/install.
- CI uses Ubuntu and Python 3.12; runner is Linux x64 with label `skif`.
- Runtime volume persists; config is `/opt/skif/.env`.
- Deployment rollback preserves database and restores code only.

### Task 1: Application readiness

**Files:** `skif_agents/health.py`, `skif_agents/__main__.py`, `tests/test_health.py`, `tests/test_cli.py`.

**Interface:** `write_heartbeat(path, release, roles, timestamp=None)` and `check_heartbeat(path, release, timestamp=None) -> bool`; `validate_telegrams(telegrams)` returns after identity/webhook checks or raises redacted error. CLI `probe` uses only getMe/getWebhookInfo. `check` returns exit 2 when configuration is incomplete.

- [ ] Write failing tests using temporary heartbeat files: good four-role release returns true, 60-second old/wrong release/missing role returns false. Invoke real CLI subprocess with an empty environment and assert check exits 2.
- [ ] Run `python -m unittest discover -s tests -p 'test_health.py' -v` and the CLI test; observe expected failures.
- [ ] Implement atomic heartbeat JSON and periodic write after Telegram startup validation; implement read-only probe and meaningful exit codes.
- [ ] Re-run targeted tests and commit.

### Task 2: Deployment transaction

**Files:** `ops/__init__.py`, `ops/deploy.py`, `tests/test_deploy.py`, `.github/workflows/ci.yml`.

**Interface:** `deploy(engine, source: Path, revision: str, home: Path, timeout: int=90)` controls build/preflight/stop/start/health/rollback. `DockerEngine` owns actual subprocess calls and fixed container `skif-bots`, image `skif-bots:<40hex>`, volume `skif_runtime`.

- [ ] Write tests with a stateful in-memory external-engine substitute; assert final running image and durable deployment receipt. Raise on overlapping instances to enforce stop-before-start. Exercise build/preflight failures, failed readiness with old version restoration, first install failure, invalid revision and held file lock.
- [ ] Run `python -m unittest discover -s tests -p 'test_deploy.py' -v`; observe failure while module is absent.
- [ ] Implement exclusive filesystem lock, bounded readiness wait, unchanged old version on preparation failure, redacted errors, JSON receipt without credentials, and rollback.
- [ ] Add CI tests on hosted Ubuntu for push/PR, and deployment only on private exact-repo main after tests. Pin official actions, disable checkout credential persistence, serialize deployment jobs.
- [ ] Run tests, Python compilation and YAML validation, then commit.

### Task 3: Owner bootstrap

**Files:** `ops/bootstrap_host.py`, `ops/README_RU.md`, `tests/test_bootstrap.py`.

**Interface:** an explicitly invoked root installer for Ubuntu 24.04. It installs distribution Docker packages, creates `skifrunner`, prepares `/opt/skif`, obtains official runner release/checksum, asks for the temporary registration token with getpass, and installs the service. Existing runner/config is preserved. Secrets are supplied on the server later.

- [ ] Validate repository allowlist, runner archive identity/digest, and rerun refusal in tests before implementation.
- [ ] Implement controlled official downloads and safe extraction, hidden token entry, separate user/service, and no automatic overwrite.
- [ ] Document that Docker membership is administrative VM access and that four rotated bot tokens, owner numeric ID and model API settings are still required.
- [ ] Test only pure validation/local extraction; do not run apt, sudo, registration or cloud operations in this workspace.

### Task 4: Delivery and truthful status

**Files:** `README.md`, `START_RU.txt`, `VERIFICATION.md`, output archive and concise start guide.

- [ ] Run complete test suite and inspect meaningful rollback failures.
- [ ] Attempt creation of the approved private repository with supported GitHub/browser capabilities, never use an unrelated public repository.
- [ ] If authentication prevents repository creation, finish all local deliverables and provide exactly the missing creation/login step; do not claim GitHub or server deployment succeeded.
- [ ] Persist the resulting package and upload it to the authorized Yandex Disk folder `Крым`; maintain separate old version.
