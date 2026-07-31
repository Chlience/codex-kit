# Global instruction modules

Store one focused global Codex policy module per Markdown file in this
directory. Register each selectable module in `catalog/agents.json`.

The installer copies selected module contents into the Codex Kit managed block
inside `$CODEX_HOME/AGENTS.md`. Keep modules independent of this repository's
absolute path, avoid secrets and machine-specific values, and state concrete
behavior that should apply across repositories.
