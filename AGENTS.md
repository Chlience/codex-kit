# Codex Kit

## Purpose

This repository bootstraps user-selected Codex skills, plugins, and global
`AGENTS.md` modules on Linux.

## Installation entry point

- Loading this repository does not authorize installation or global changes.
- Start installation only when the user explicitly asks to install, bootstrap,
  configure, or repair Codex from this repository.
- For an installation request, read
  `.agents/skills/install-codex-kit/SKILL.md` completely and follow it.
- Require the user to select items and approve the concrete write plan.

## Repository maintenance

- Keep `catalog/*.json` valid JSON with `schema_version` set to `2`.
- Keep catalog IDs unique within each catalog.
- Keep selectable first-party Skills under `bundled/skills/<skill-id>/`; only
  the bootstrap Skill belongs under `.agents/skills/`.
- Before publishing a bundled Skill, audit it for secrets, personal data,
  machine-specific paths, private URLs, local state, executable behavior, and
  redistribution rights.
- Give each bundled Skill its own license file so the license remains attached
  when the Skill is installed independently.
- Keep rule modules under `agents/modules/` and reference them with
  repository-relative paths.
- Do not commit secrets, credentials, machine-specific absolute paths, or local
  installation state.
- Prefer the current installation mechanism documented by each upstream
  repository and by Codex.
- Preserve existing user configuration outside explicitly marked managed
  regions.
- Validate the bootstrap skill and all catalogs after changing installation
  behavior.
