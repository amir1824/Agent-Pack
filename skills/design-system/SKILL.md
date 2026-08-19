---
name: design-system
description: Reuse the project's existing components, spacing, and colors instead of inventing new ones.
---

# Design system adherence

This is the concrete form of the constitution's "do not invent UI components,
spacing, or hardcoded colors when the project already has them."

## Before adding any UI

1. Search for an existing component that does this already, even
   approximately — extend it rather than duplicating it.
2. Use the project's spacing scale/tokens, not a literal pixel value picked by
   eye.
3. Use the project's color tokens/theme variables, not a hardcoded hex value —
   including in one-off inline styles.
4. If the project has both light and dark themes, any new color must be
   defined for both, not just whichever one you're looking at.

## When there is genuinely no existing pattern

Say so explicitly, and propose the new component/token as a first-class
addition to the design system (so the next person reuses it too) rather than
a one-off buried in a single feature.

## Red flags in review

- A hex color or raw `px` value that doesn't match anything else in the
  codebase.
- A new button/card/modal component that duplicates one that already exists
  under a different name.
- Copy-pasted styling instead of a shared class/token.
