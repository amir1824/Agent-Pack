---
name: api-contract
description: Rules for changing an API or data contract without breaking existing callers.
---

# API contract changes

Applies to HTTP endpoints, function signatures other code depends on, CLI
flags, file formats, and any schema another system reads.

## Before changing a contract

- Identify every caller/consumer of the current shape. If you can't find them
  all, treat the change as breaking and version it rather than guessing it's
  safe.
- Prefer additive changes: a new optional field, a new endpoint, a new
  argument with a default — over renaming or removing an existing one.
- If a field or endpoint must be removed, deprecate first (keep it working,
  mark it deprecated, give consumers a migration path) rather than deleting it
  in the same change that stops using it.

## When a breaking change is unavoidable

- Bump the version that signals it (semver major, an API version segment, a
  schema version field — whatever this project already uses).
- Update every caller in the same change; a contract change with an unmodified
  caller is not done.
- State explicitly in the change description what breaks and what the
  migration is — don't leave it to be discovered.

## Review checklist

- Does every consumer of the changed contract still compile/pass tests?
- Is the change additive, or does it require every caller to update *now*?
- Is there a version bump if this is genuinely breaking?
