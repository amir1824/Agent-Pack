---
name: retrospective
description: How to run a retrospective on a completed delivery run and turn findings into a proposed pack change.
---

# Retrospective

A retrospective is triggered by a human, after they've reviewed a completed
run — never automatically, and never as part of the run being reviewed. It is
its own run, started with `--from-run` so its plan is exactly the agents that
actually participated, not a fixed roster:

```bash
pack record start --profile-id retrospective --request "retro on <run-id>" \
  --from-run <run-id>
```

## Each agent's turn

You are reflecting on your own track record, not on this one run in
isolation. Pull your history across every run first:

```bash
pack log --agent <your-step-name>
```

Then write your step:

```bash
pack record step --id <retro-id> --name <your-step-name> --status done \
  --detail "<finding>"
```

A finding is worth writing only if it's a real pattern (recurring friction,
a gap the constitution or a skill should have caught, something you'd tell
the next person to run this role) — not a play-by-play of this one run. If
there's nothing worth flagging, record `--status done` with a short
`--detail "nothing to flag"` rather than manufacturing a finding.

## What a finding is not

A finding is not a request to change your own behavior right now — a
prompted agent doesn't retain that. The only durable place a finding can land
is the pack: an edit to a skill or a profile's `instructions`. State the
finding as a proposed change: what file, what would change, why it would
have prevented the friction you saw. Do not edit the pack repo yourself —
for now, findings are surfaced for a human to read and apply by hand:

```bash
pack log --agent <your-step-name> --export findings.json
```

## Closing the loop (out of scope for this skill)

Once findings are reviewed and applied to a skill or profile in the pack
repo, that change is validated, tagged, and reaches every consumer through
the normal `pack upgrade` path — same as any other pack edit. Nothing about
a retrospective finding is special once it becomes a pack change; the
retrospective's only job is to produce a finding worth acting on.
