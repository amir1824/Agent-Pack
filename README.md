# pack

CLI that binds one tagged pack git repo to an app, syncs skills and profiles as real md/yaml files, pins them in `agent-pack.lock.json`, and reads a run log.

This repository is the pack source (`pack.yaml`, `skills/`, `profiles/`, `AGENTS.md`, `constitution.md`) and the CLI.

## Install

```bash
pip install -e .
```

## Pack repo

```bash
pack init
pack validate
git add pack.yaml AGENTS.md constitution.md skills profiles
git commit -m "feat: initial pack"
git tag v1.0.0
```

## App repo

```bash
pack bind <pack-git-url> --tag v1.0.0
pack sync
pack status
pack check
pack diff
pack upgrade --tag v1.1.0
pack log
pack dashboard
pack dashboard --open
pack record start --profile-id generic-agent --request "demo"
pack record complete --id <invocation-id> --outcome done
```

`-C <dir>` targets an existing checkout. `--repo <app-url>` clones the app first, then runs the same command.

`sync` overwrites files that came from the pack: `.agents/`, host copies under `.cursor/skills/` and `.claude/skills/`, generated `.claude/agents/`, and a marked block in root `AGENTS.md` (constitution above agents). It does not delete host files that were never in the lockfile. It also writes the lockfile and a `.agents/log/` line in `.gitignore`.

`check` prints the same report as `status` and exits 1 if the consumer is dirty or not synced. `record` writes JSONL under `.agents/log/`. `dashboard` serves a localhost UI of skills, profiles, constitution, and run flow (`--kill` stops it; `--json` prints the snapshot).
