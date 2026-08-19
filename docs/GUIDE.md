# Guide: using agent-pack in a real project

This walks through the tool as it exists today: one pack repo (this one), bound and
synced into one or more app repos. It does not cover machine-level (`~/.claude`)
sync, an override layer for editing a pack file locally, or multiple packs per
consumer — those aren't built yet.

## 0. What this repo already is

This repo is the **pack repo**: [pack.yaml](../pack.yaml), [skills/](../skills/),
[profiles/](../profiles/), [constitution.md](../constitution.md),
[AGENTS.md](../AGENTS.md). You edit those files here. Any number of app repos can
bind to a tag of this repo and pull them in.

## 1. Install the CLI

Two different installs, for two different people. Both put the same `pack`
command on `PATH` — the difference is whether you also get a checkout of this
repo's source.

**You, working on the CLI itself:** clone and install editable, so a change to
`src/agent_pack/` is live immediately.

```bash
git clone git@github.com:amir1824/Agent-Pack.git && cd Agent-Pack
pip install -e .
```

**Everyone else — anyone who just wants the `pack` command:** no clone, and
`pip install` straight into a system/global Python is an antipattern (fights
other packages, and modern Python refuses it outright). Use
[pipx](https://pipx.pypa.io/) instead — it's the standard way to install a
Python CLI tool: an isolated venv per tool, only the entry point (`pack`) lands
on `PATH`.

```bash
pipx install "git+https://github.com/amir1824/Agent-Pack.git@v1.0.0"
# private repo: use ssh, same as pack bind — see README: Authentication
pipx install "git+ssh://git@github.com/amir1824/Agent-Pack.git@v1.0.0"
```

pipx shells out to `pip`, which shells out to `git`, so this needs a tag to
exist first (step 2 below) — there isn't one yet. Pin the tag explicitly rather
than leaving it off: this repo's CLI code and its pack content
(`skills/`, `profiles/`, `constitution.md`) are versioned together, in the same
tags, so `@v1.0.0` here fixes which build of `pack` you get, separately from
whatever tag a given app repo later binds to for content (step 3). Upgrade with
`pipx install --force "...@v1.1.0"`.

## 2. Tag a release of the pack

`pack bind` pins a git **tag**, not a branch — so the pack repo needs at least one
tag before anything can consume it.

```bash
pack validate
git add pack.yaml AGENTS.md constitution.md skills profiles
git commit -m "feat: initial pack"
git tag v1.0.0
git push && git push --tags   # only if this repo has a remote
```

`pack validate` catches the things that block a consumer sync before you tag: a
skill's frontmatter `name` not matching its folder, a missing `description`, a
duplicate `profile-id`, an empty `constitution.md`, or a symlink anywhere under
`skills/`/`profiles/`.

## 3. Bind an app repo to the pack

In the app repo you actually want the skills/profiles/constitution in:

```bash
cd ~/code/my-app
pack bind git@github.com:org/agent-pack.git --tag v1.0.0
```

Private repo → use an SSH url like the one above; your `ssh-agent` key does the
rest, `pack` never touches a credential. See
[README: Authentication](../README.md#authentication) for the HTTPS case and why a
token embedded in the URL is rejected outright.

Working on the pack and an app side by side on the same machine, before pushing
anything? Bind to the local path instead — same command, just a path in place of
a URL:

```bash
pack bind /Users/amirbenshimol/Agent-Pack --tag v1.0.0
```

`-C <dir>` targets a checkout that isn't your current directory, and `--repo
<app-url>` clones the app first and runs there — both work with every command
below, not just `bind`.

## 4. Sync

```bash
pack sync
```

This writes, under the app repo root:

| Path | What lands there |
|---|---|
| `.agents/` | Verbatim copy of the pack: `pack.yaml`, `AGENTS.md`, `constitution.md`, `skills/`, `profiles/` |
| `.cursor/skills/<id>/SKILL.md` | One projection per skill |
| `.claude/skills/<id>/SKILL.md` | Same skill, Claude's path |
| `.claude/agents/<profile-id>.md` | Each profile rendered as a Claude subagent (frontmatter `name`/`description` + `instructions`) |
| `AGENTS.md` (repo root) | `constitution.md` + the pack's `AGENTS.md`, inside a marked `<!-- agent-pack:start -->…<!-- agent-pack:end -->` block — anything else already in your root `AGENTS.md` is left alone |
| `agent-pack.lock.json` | Name, source, tag, resolved commit, and a sha256 per synced file — **commit this** |
| `.gitignore` | Gets a `.agents/log/` line added if it isn't there |

Everything under `.agents/`, `.cursor/skills/`, `.claude/skills/`, and
`.claude/agents/` that came from the pack is now **pack-managed: treat it as
read-only**. Editing one of those files directly gets silently overwritten on the
next `pack sync` — there's no override layer yet, so if a skill or profile needs
to change, change it in the pack repo (step 6) and re-sync.

## 5. Day-to-day: status, check, diff

```bash
pack status   # name / source / tag / commit + dirty state
pack check    # same report, exits 1 if dirty or not synced — wire into CI/pre-commit
pack diff     # unified diff between .agents/ and what the pinned tag currently has
```

A repo is **dirty** if a pack-managed file was edited or deleted (`modified` /
`missing`). Only `.agents/` is tracked for this — a file you add yourself under
`.agents/skills/<your-skill>/SKILL.md` shows up as `extra` and does **not** fail
`check`; that's expected, not drift.

That tracking does not reach `.cursor/skills/` or `.claude/skills/` directly:
`sync` only ever writes there, it never reads them back. So a skill you drop
straight into `.claude/skills/<your-skill>/` is picked up by Claude but is
completely invisible to `pack status`/`check` — not `extra`, not `dirty`, just
unmanaged. Either is a legitimate way to add a project-only skill; `.agents/`
just also gets you visibility in `pack status` and the dashboard. Either way it
stays local to this repo — if you want it shared across consumers, put it in the
pack instead (step 6).

## 6. Editing a skill or profile (the actual day-2 workflow)

Always in the **pack repo**, never in a consumer:

```bash
# edit skills/<id>/SKILL.md or profiles/<id>.agent.yaml here
pack validate
git commit -am "feat: tighten the verifier profile"
git tag v1.1.0
git push && git push --tags
```

Then in each consumer:

```bash
pack upgrade --tag v1.1.0   # or omit --tag to take the latest tag
```

`pack upgrade` re-syncs and moves the lockfile's pinned tag/commit forward. Files
the new tag no longer ships (e.g. you deleted a skill) are removed from the
consumer; your `extra` files are never touched.

### If a tag gets force-moved

Git tags are mutable. If `v1.1.0` in the pack repo gets re-tagged onto a different
commit after a consumer already pinned it, `pack sync` refuses to copy anything
and fails loudly instead of silently swapping what your agents get told:

```
error: pinned tag v1.1.0 moved: lockfile has <old-sha>, <source> now resolves to <new-sha>.
  Nothing was copied. Inspect with pack diff, then accept with
  pack upgrade --tag v1.1.0  (or pack sync --allow-tag-move)
```

Run `pack diff` to see what actually changed before accepting it with `pack
upgrade --tag v1.1.0` (the sanctioned way to move a pin) or `pack sync
--allow-tag-move` if you already know what you're accepting.

## 7. Wire `pack check` into CI

This runs in the **app repo's** CI, so it needs the `pack` CLI installed from
the pack repo's source — not `pip install -e .`, which would try to install the
app repo itself as a package.

```bash
pip install "git+https://github.com/amir1824/Agent-Pack.git@v1.0.0"
pack -C . check
```

Fails the build if someone edited a pack-managed file directly in the app repo
instead of going through the pack, or if the repo was never synced. It does not
fail on `extra` files, and it does not hit the network — it only compares local
hashes against `agent-pack.lock.json`.

## 8. Track agent runs

```bash
pack record start --profile-id generic-agent --request "add checkout flow"
# -> prints an invocation id; the plan comes from generic-agent's `plan:`
#    (product, designer, developer-api, developer-ui, qa) — pass --plan to
#    override it for a one-off run

pack record step --id <id> --name product --status started --detail "PRD drafted"
pack record step --id <id> --name product --status done    --detail "scope locked"
...
pack record complete --id <id> --outcome done   # done | failed | abandoned

pack log              # table of recent runs
pack dashboard --open # visual view: skills, profiles, constitution, run flow
```

Once a run has a plan (from the profile or from `--plan`), the log enforces it:
`record step --name <x>` fails if `<x>` isn't a planned step, and `record
complete --outcome done` fails if a planned step never reached `done`. Both
take `--force` to override — `failed` and `abandoned` are never blocked, since
that's how you record a run that didn't finish.

Each `started` event also records `pack_name`/`pack_tag`/`pack_commit` from
`agent-pack.lock.json` — which pin was in force, i.e. which version of the
constitution and skills governed that run. Two runs recorded before and after
a `pack upgrade` carry different tags/commits, so the log can answer "under
which constitution did this run happen?" without cross-referencing anything
else.

Runs are JSONL under `.agents/log/`, gitignored by default — local
observability, not durable on its own. To keep a run as evidence rather than
losing it with the checkout, export it:

```bash
pack log --export runs.json   # every run as one JSON array
```

Upload `runs.json` as a CI artifact, or archive it wherever your team keeps
audit records — not inside the app repo, since it carries `request_text` for
every run.

### Retrospective

After you've reviewed a completed run yourself — this is never automatic —
run a retrospective on it. It's its own run, not a step tacked onto the one
being reviewed, and its plan comes from who actually participated rather
than a fixed roster:

```bash
pack record start --profile-id retrospective --request "retro on <run-id>" \
  --from-run <run-id>
```

Each agent that shows up in that plan pulls its own history across *every*
run it's ever been part of — not just this one — before writing a finding:

```bash
pack log --agent qa                              # table
pack log --agent qa --export qa-findings.json     # for a human to read
```

See [skills/retrospective](../skills/retrospective/SKILL.md) for what counts
as a finding worth recording. Findings don't change anything by themselves —
turning one into an actual improvement means a human reads it and edits the
relevant skill or profile in the pack repo, the same way any other pack
change ships (validate, tag, `pack upgrade`).

## Command reference

| Command | Does |
|---|---|
| `pack init [--name]` | Scaffold a new pack repo (`pack.yaml`, `AGENTS.md`, `constitution.md`, an example skill, two profiles) |
| `pack validate` | Check the pack repo's structure before tagging (frontmatter, ids, and a profile's `plan:` if it has one) |
| `pack bind <git_url\|path> [--name] [--tag]` | Point this app at a pack + tag (defaults to the latest tag) |
| `pack sync [--allow-tag-move]` | Copy the pinned tag into `.agents/` + host projections |
| `pack status` | Print name/source/tag/commit + dirty state |
| `pack check` | Same as `status`, exit 1 if dirty or unsynced — CI gate |
| `pack diff` | Diff `.agents/` against what the pinned tag has now |
| `pack upgrade [--tag]` | Move the pin (default: latest tag) and sync |
| `pack log [-n] [--export <path>]` | Print recent runs, or export every run as JSON |
| `pack log --agent <name> [--export <path>]` | One agent's steps across every run, not the per-run table |
| `pack record start [--plan] [--from-run <id>]` | Write a started event; plan defaults to the profile's `plan:`, or `--from-run` derives it from who actually ran in a prior invocation |
| `pack record step [--force]` | Write a checkpoint; rejects a name outside the run's plan unless `--force` |
| `pack record complete [--force]` | Write a completed event; `--outcome done` is blocked by an unfinished planned step unless `--force` |
| `pack dashboard [--port] [--open] [--kill] [--json]` | Local dashboard over the pack/consumer state |

`-C <dir>` and `--repo <url>` are global flags accepted before the subcommand on
every command above.

## What's not here yet

- **No override layer.** Editing a pack-managed file locally doesn't persist — it's
  overwritten on the next `sync`. Only additions (`extra`) survive.
- **One pack per consumer.** `pack bind` fails if the app repo is already bound;
  there's no notion of a base pack plus a team pack plus a personal pack.
- **No machine-level sync.** Everything lands under the app repo root; there's no
  `pack sync --global` for `~/.claude/skills/` yet.

See [docs/ROADMAP.md](ROADMAP.md) for the full list of what's built vs. planned.

See [README.md](../README.md) for install, project layout, and the authentication
model in full.
