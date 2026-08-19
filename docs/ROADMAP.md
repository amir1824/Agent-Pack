# Roadmap: closing the gaps

Status as of 2026-08-19. Phase 1 (real content) and Phase 2 (governance) are
**implemented and tested** — see [Done](#done-2026-08-19) below. Phase 0's code
prerequisites are covered by that work; what's left of Phase 0 is git ceremony
(commit, tag, push) that wasn't run as part of this pass — see
[Still open](#still-open). Distribution work (override layer, `sync --global`,
multiple packs per consumer) is deliberately deferred — see [Deferred](#deferred).

**Decisions taken:** CLI and pack content stay in one repo on shared tags for now.
The run log becomes compliance evidence, not just local observability.

## Done (2026-08-19)

- **Phase 1** — [skills/code-review](../skills/code-review/SKILL.md),
  [skills/design-system](../skills/design-system/SKILL.md),
  [skills/api-contract](../skills/api-contract/SKILL.md) replace the
  placeholder; [generic-agent](../profiles/generic-agent.agent.yaml) plus five
  role profiles (product, designer, developer-api, developer-ui, qa) replace
  the two thin ones.
- **2a** — `plan:` is a validated field on a profile
  ([validate.py](../src/agent_pack/pack/validate.py)); `record_start` reads it
  from the synced (or pack-repo) profile when `--plan` is omitted
  ([record.py](../src/agent_pack/log/record.py)); surfaced in the dashboard
  snapshot and `Profile` type.
- **2b** — `record_step` rejects a name outside the run's plan;
  `record_complete --outcome done` refuses to close until every planned step
  is `done`; both accept `--force`. `failed`/`abandoned` are never blocked.
- **2c** — `started` events carry `pack_name`/`pack_tag`/`pack_commit` from
  `agent-pack.lock.json`; absent (not erroring) for a pack-repo-only run. Shown
  as a chip on run cards and in the run drawer.
- **2d** — `pack log --export <path>` writes every run as a JSON array.
  `_LOG_README`/`_LOG_SCHEMA` document the pin fields and the export/retention
  pattern.
- **Retrospective loop** (2026-08-19) — [skills/retrospective](../skills/retrospective/SKILL.md)
  + [profiles/retrospective.agent.yaml](../profiles/retrospective.agent.yaml).
  Human-triggered only, never automatic, and modeled as its own run rather
  than a step embedded in the delivery plan (so it can't block `record
  complete` on the run it's reviewing). `record start --from-run <id>`
  derives the plan from who actually participated in that run — not a
  static roster, so a skipped role doesn't get an empty retro slot.
  `pack log --agent <name>` / `pack log --agent <name> --export` give each
  agent its own cross-run history — the concrete answer to "give it what it
  needs" for a finding to be more than a one-run anecdote. Findings land as
  free text for now; turning them into pack-repo diffs is deliberately
  manual (a human reads and edits) — see [Deferred](#deferred).

73 tests pass (up from 55); `npm run build` + `tsc --noEmit` are clean and the
committed bundle matches. New coverage:
[tests/test_plan_from_profile.py](../tests/test_plan_from_profile.py),
[tests/test_plan_enforcement.py](../tests/test_plan_enforcement.py),
[tests/test_run_provenance.py](../tests/test_run_provenance.py) (also covers
export). [LICENSE](../LICENSE) (MIT) was added and referenced from
[pyproject.toml](../pyproject.toml).

## Still open

Nobody ran `git commit`, `git tag`, or `git push` as part of this pass — this
session makes working-tree changes; git ceremony has consistently been run
separately. Before any of this is reachable via `pack bind`/`pipx install`:

```bash
git add -A && git commit -m "..."
pack validate
git tag v0.1.0 && git push && git push --tags
```

Then confirm [.github/workflows/ci.yml](../.github/workflows/ci.yml) actually
goes green on the push — it has still never run.

---

## Phase 1 — Real pack content (done)

Shipped [skills/code-review](../skills/code-review/SKILL.md),
[skills/design-system](../skills/design-system/SKILL.md), and
[skills/api-contract](../skills/api-contract/SKILL.md) in place of the old
placeholder `example` skill. [generic-agent](../profiles/generic-agent.agent.yaml)
now carries a full `plan:` and instructions; five role profiles (product,
designer, developer-api, developer-ui, qa) sit alongside
[verifier](../profiles/verifier.agent.yaml).

`init_pack` still scaffolds an `example` skill for fresh repos; the pack repo
itself no longer ships one. Tests that exercise sync/status use the scaffold;
the real pack tree is covered by `pack validate` on this repo.

---

## Phase 2 — Governance: make the workflow a pinned artifact (done)

This is the differentiator identified in the market review: Spec Kit, Kiro and
Spec Kitty all keep the constitution and workflow **per-repo**; APM distributes
and pins but has no constitution or run log. The crossing — governance pinned
across a fleet *and* runs recorded against that pin — is only reachable if the
workflow itself is pack-managed.

### 2a. Move `plan` from a CLI flag into the profile

Today `--plan product,designer,qa` is retyped by hand at every `pack record start`
([cli.py:91](../src/agent_pack/cli.py:91)). It is the one piece of the system that
is *not* versioned, pinned, or distributed — which defeats the premise.

- Add an optional `plan: [ ... ]` list to `profiles/<id>.agent.yaml`.
- Validate it in `_validate_profile` ([validate.py:64](../src/agent_pack/pack/validate.py:64)):
  a list of non-empty unique strings.
- `record_start` ([record.py:29](../src/agent_pack/log/record.py:29)) reads the plan
  from the synced profile at `.agents/profiles/<profile-id>.agent.yaml` when
  `--plan` is omitted. Keep `--plan` as an explicit override for ad-hoc runs.
- Surface it in the dashboard: `_profiles` ([snapshot.py:69](../src/agent_pack/dashboard/snapshot.py:69))
  already reads profile YAML, so add `plan` to the emitted dict and to the
  `Profile` type in [types.ts](../src/agent_pack/dashboard/ui/types.ts).

### 2b. Enforce the plan

`record_step` only checks that the status is legal and the name is non-empty
([record.py:64](../src/agent_pack/log/record.py:64)); `record_complete` never
checks the steps at all. A run can today declare `--outcome done` having recorded
nothing.

- `record_step` rejects a `--name` not in the run's plan (when the run has one).
- `record_complete --outcome done` fails if any planned step never reached `done`.
  `failed` and `abandoned` stay unconditional — they are how you record a run that
  did not finish.
- Add `--force` for the escape hatch, so the gate is bypassable but never silent.

### 2c. Bind the log to the pin

The single highest-value change in the whole roadmap, and among the smallest.
`record_start` records `profile_id`, `request_text`, `started_at`, `plan` — but
not which pack version was in force, so the log cannot answer "under which
constitution did this run happen?".

- In `record_start`, read [agent-pack.lock.json](../src/agent_pack/sync/lockfile.py)
  and write `pack_name`, `pack_tag`, `pack_commit` into the `started` event.
  `_require_record_root` ([record.py:23](../src/agent_pack/log/record.py:23))
  already proves a lockfile or `pack.yaml` is present, so the read is safe; make
  the fields optional for a pack-repo-only run with no lockfile.
- Add them to `Run` / `Run.as_dict` ([record.py:105](../src/agent_pack/log/record.py:105))
  and to `parse_run`.
- Update `_LOG_SCHEMA` in [scaffold.py](../src/agent_pack/log/scaffold.py) — it is
  the documented contract and will otherwise drift.
- Show the pin on the run in the dashboard drawer.

### 2d. Make the log durable

`.agents/log/` is gitignored ([gitignore.py:5](../src/agent_pack/sync/gitignore.py:5)),
so today the evidence dies with the working copy. Compliance evidence has to
outlive the machine.

- Add `pack log --export <path>` (or `--json`) emitting all runs as a single
  JSON/JSONL document suitable for archiving as a CI artifact.
- Leave the gitignore default as-is — committing raw run logs to app repos would
  be noisy and would leak `request_text`. Document the archive-from-CI pattern in
  [GUIDE.md](GUIDE.md) step 8 instead.
- Update `_LOG_README` in scaffold.py, which currently states the directory is
  gitignored without saying what to do about retention.

---

## Verification (run 2026-08-19)

```bash
python -m pytest -q          # 73 passed (was 55)
npm run build                # tsc --noEmit clean, bundle rebuilt
git diff --exit-code src/agent_pack/dashboard/static/app.js   # bundle matches
```

New tests, following the `PackRepoTest` fixture in [tests/test_cli.py:31](../tests/test_cli.py:31):

- [tests/test_plan_from_profile.py](../tests/test_plan_from_profile.py) (2a) —
  a profile with `plan:` drives `record start` with no `--plan`; `--plan` still
  overrides; empty/duplicate `plan` entries fail `pack validate`.
- [tests/test_plan_enforcement.py](../tests/test_plan_enforcement.py) (2b) — a
  step name outside the plan is rejected; `complete --outcome done` fails with
  an unfinished planned step and succeeds once all are `done`; `--force`
  bypasses both; `failed`/`abandoned` are never blocked; a run with no plan is
  never blocked.
- [tests/test_run_provenance.py](../tests/test_run_provenance.py) (2c, 2d) —
  `started` carries the lockfile's `pack_tag`/`pack_commit`; a run before
  `pack upgrade` and a run after it carry different tags/commits; a
  pack-repo-only run has none; the dashboard snapshot surfaces the pin;
  `--export` round-trips every run including an empty log.

---

## Deferred

Distribution changes, all requiring lockfile-format or CLI design work:

- **Override layer** — a declared `pack.local.yaml` so a locally edited pack file
  survives `sync` instead of being silently overwritten. Only additions (`extra`)
  survive today. The constitution should stay non-overridable — that is what makes
  it a constitution.
- **`pack sync --global`** — machine-level install into `~/.claude/skills/`,
  `~/.claude/agents/`, and a marked block in `~/.claude/CLAUDE.md`. Verified
  reachable today via `-C ~`, but it litters the home dir with `~/.agents/`,
  `~/AGENTS.md`, `~/.gitignore`, and puts the constitution in a file Claude Code
  does not read at user level.
- **Multiple packs per consumer** — org base + team + personal, in precedence
  order. `bind` currently refuses a second pack
  ([consumer.py:42](../src/agent_pack/sync/consumer.py:42)). Worth shaping the
  lockfile as a list *before* v1.0.0 so this is not a breaking format change later.
- **Retrospective findings → pack diffs automatically** — right now a human
  reads `pack log --agent <name>` output and edits the pack repo by hand. A
  `retrospective-facilitator` profile that reads findings and proposes a
  concrete diff (for the verifier profile to review before merge) is the
  natural next step, once the manual loop has run enough times to know what
  a good finding actually looks like.
- **Project the constitution into other SDD tools** — `.specify/memory/constitution.md`
  (Spec Kit) and `.kiro/steering/` (Kiro), via a new branch in `projected_paths`
  ([adapters.py:20](../src/agent_pack/sync/adapters.py:20)). Roughly ten lines, and
  it turns `pack` into the governance layer *under* Spec Kit rather than a
  competitor to it.
