---
name: code-review
description: Checklist for reviewing a change before it merges — correctness, contracts, secrets, and reuse over new code.
---

# Code review

Apply this before approving any change, not just when asked to "review."

## Block on

- A behavior change with no updated test covering it.
- An API or data contract that changed without every caller being updated in
  the same change.
- A secret, token, or credential in source, a config file, or a URL.
- New UI: components, spacing, or colors invented instead of reusing what the
  project already has (see [design-system](../design-system/SKILL.md)).
- Error handling that swallows an exception without logging or surfacing it.

## Prefer

- Reusing an existing utility/function over writing a new one that does the
  same thing slightly differently.
- The smallest diff that fully solves the stated problem — no drive-by
  refactors bundled into a functional change.
- Matching the surrounding code's naming, structure, and comment density
  rather than introducing a new style.

## Output

State findings as: what's wrong, where (file:line), and the concrete failure
case it causes — not a rewrite. A block with a reason beats a suggestion
nobody has to act on.
