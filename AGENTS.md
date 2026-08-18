# Agents

Skills and profiles for this team live in the pack repository.

- Skills: `skills/<id>/SKILL.md`
- Profiles: `profiles/<id>.agent.yaml`
- Constitution: `constitution.md` (must / must not)

In an application repo, `pack sync` copies them to `.agents/` and projects skills into `.cursor/skills/` and `.claude/skills/`, profiles into `.claude/agents/`, and a marked block into root `AGENTS.md`. Edit only in this pack; never push consumer edits back upstream.
