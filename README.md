# pack

CLI that binds one tagged pack git repo to an app, syncs skills and profiles as real md/yaml files, pins them in `agent-pack.lock.json`, and reads a run log.

This repository is the pack source (`pack.yaml`, `skills/`, `profiles/`, `AGENTS.md`, `constitution.md`) and the CLI.

## What it does

`pack` manages an “agent skills pack” and syncs it into application repos:

- Create and validate a pack repository (`pack init`, `pack validate`)
- Bind a consumer app to a specific pack tag (`pack bind`)
- Sync pack-managed files into the app (`pack sync`) including host projections for Cursor/Claude
- Inspect consumer state and changes (`pack status`, `pack diff`, `pack check`, `pack upgrade`)
- Record run logs and expose them in a local dashboard (`pack record ...`, `pack dashboard`)

## What problem it solves

It replaces manual copy/paste and ad-hoc synchronization with a deterministic, version-pinned workflow:

- One team source of truth for skills/profiles (the pack repo), with reproducible consumer deployments via a pinned lockfile
- Clear verification boundaries (validation + gitignore rules + logged run events under `.agents/log/`)
- Less drift between environments by automatically projecting pack files into the correct `.cursor/` and `.claude/` locations

## Authentication

`pack` runs git as a subprocess and never handles credentials itself. Nothing secret is
stored in `agent-pack.lock.json`, which is meant to be committed.

**SSH is the supported path for a private pack repo:**

```bash
pack bind git@github.com:org/team-pack.git --tag v1.0.0
pack bind ssh://git@github.com/org/team-pack.git --tag v1.0.0
```

Keys come from your `ssh-agent` / `~/.ssh/config` as usual. `pack` runs git with
`BatchMode=yes` and `GIT_TERMINAL_PROMPT=0`, so a missing key fails immediately with a
clear message instead of hanging on a prompt.

**HTTPS works only through a git credential helper:**

```bash
pack bind https://github.com/org/team-pack.git --tag v1.0.0
```

A credential in the URL is rejected — `https://<token>@github.com/...` would be written
verbatim into the committed lockfile. Configure `git config --global credential.helper`
(or `gh auth login`) instead.

Sources are checked before git sees them: values starting with `-` (which git would read
as an option, e.g. `--upload-pack=`) and shell transports such as `ext::` are refused.

Note that `git@host:org/repo.git` and `ssh://git@host/org/repo.git` hash to different
cache entries and count as different pins. Pick one form per pack and stay with it.

## Pin integrity

Git tags are mutable, and a pack tag controls what `.claude/agents/` and `AGENTS.md` tell
your agents to do. `pack sync` therefore verifies that the pinned tag still resolves to
the commit in the lockfile:

```
error: pinned tag v1.0.0 moved: lockfile has 4f2a1c8b90de, /srv/team-pack now resolves to 9c31de07ab44.
  Nothing was copied. Inspect with pack diff, then accept with
  pack upgrade --tag v1.0.0  (or pack sync --allow-tag-move)
```

Nothing is written until the pin is accepted. `pack upgrade` is the sanctioned way to move
a pin; `pack diff` prints a warning banner and shows the incoming content.

## Install

```bash
pip install -e .
```

## Project structure

```
src/agent_pack/
  cli.py              entry point (pack = agent_pack.cli:main)
  errors.py            shared exceptions
  target.py            --repo clone helper

  pack/                pack-repo primitives
    source.py          init, iterate, hash, frontmatter
    validate.py        structural validation

  sync/                consumer-side operations
    consumer.py        bind, sync, status, diff, upgrade
    adapters.py        host projections + root AGENTS.md block
    lockfile.py        agent-pack.lock.json read/write
    gitignore.py       ensure_gitignore + GITIGNORE_RULE

  git/                 git subprocess helpers
    source.py          bare cache, fetch, clone, tags

  log/                 run-log recording
    record.py          start, step, complete, list, format
    parse.py           JSONL parsing + step aggregation
    scaffold.py        log dir + schema + README scaffold

  dashboard/           localhost ops UI
    server.py          HTTP server (serves static/)
    lifecycle.py       start/kill/meta
    snapshot.py         JSON snapshot builder
    static/            app.js, app.css, index.html (committed)
    ui/                TypeScript sources (app, flow, views, …)
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
pack log --export runs.json
pack dashboard
pack dashboard --open
pack record start --profile-id generic-agent --request "demo"   # plan comes from the profile's `plan:`
pack record step --id <invocation-id> --name product --status started --detail "PRD + acceptance criteria"
pack record step --id <invocation-id> --name product --status done --detail "scope locked"
pack record complete --id <invocation-id> --outcome done
```

`-C <dir>` targets an existing checkout. `--repo <app-url>` clones the app first, then runs the same command.

`sync` overwrites files that came from the pack: `.agents/`, host copies under `.cursor/skills/` and `.claude/skills/`, generated `.claude/agents/`, and a marked block in root `AGENTS.md` (constitution above agents). It does not delete host files that were never in the lockfile. It also writes the lockfile and a `.agents/log/` line in `.gitignore`.

A profile's optional `plan:` list is the run's default checklist: `record step` rejects a step name outside it and `record complete --outcome done` refuses to close the run until every planned step is `done` — both accept `--force`. Each `started` event also records the bound pack's `pack_tag`/`pack_commit`, so a run's log states which pinned version of the constitution and skills was in force. See [docs/GUIDE.md](docs/GUIDE.md) for the full walkthrough.

`check` prints the same report as `status` and exits 1 if the consumer is dirty (a pack-managed file was edited or deleted) or not synced. Files you add under `.agents/` or a host skills dir that the pack never shipped are reported as `extra` but do not fail `check` — adding your own skills alongside the pack's is expected, not drift. `record` writes JSONL under `.agents/log/` (`start`, `step` checkpoints, `complete`). `dashboard` serves a localhost UI of skills, profiles, constitution, and run flow (`--kill` stops it; `--json` prints the snapshot).

### Dashboard UI (TypeScript)

Sources live in `src/agent_pack/dashboard/ui/`. Built JS is committed under `static/` so runtime needs no Node:

```bash
npm install
npm run build          # → static/app.js
npm run build:watch    # rebuild on change
pack dashboard --open
```
