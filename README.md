# Codex Kit

Codex Kit is a small, Git-backed bootstrap environment for moving selected
Codex capabilities between Linux machines. It keeps a catalog of Skills,
plugins, and global instruction modules while delegating installation to Codex
and each upstream project's supported tools.

The catalog starts with a reviewed repository-level source for
`mattpocock/skills`, the bundled first-party `sjl-skill`, and five selectable
global instruction modules. Additional capabilities are added only after
reviewing their source and desired behavior.

Requirements: Linux, Git, a current Codex CLI, and Python 3.10 or newer.
Selected upstream installers may add their own runtime requirements.

## Quick start

Open this repository with a plain Codex installation and explicitly invoke the
repository bootstrap Skill:

```text
Use $install-codex-kit to set up this machine from the current repository.
```

The installer presents separate lists for:

1. standalone Skills and repository-level Skill sources;
2. Codex plugins;
3. global `AGENTS.md` modules.

Nothing is installed until the user selects items and approves the resulting
commands, paths, and configuration diff. Selecting a repository-level source
opens a second checklist populated from the reviewed upstream commit; the user
then selects individual Skills from that repository.

## Repository layout

```text
.
├── AGENTS.md
├── README.md
├── .agents/
│   └── skills/
│       └── install-codex-kit/
│           ├── SKILL.md
│           └── agents/openai.yaml
├── catalog/
│   ├── skills.json
│   ├── plugins.json
│   └── agents.json
├── bundled/
│   └── skills/
│       └── sjl-skill/
├── agents/
│   └── modules/
├── scripts/
│   └── codex_kit.py
└── tests/
    └── test_codex_kit.py
```

- `AGENTS.md` routes explicit setup requests to the bootstrap Skill.
- `catalog/skills.json` lists standalone Skill sources.
- `catalog/plugins.json` lists Codex plugin and marketplace sources.
- `catalog/agents.json` lists selectable global instruction modules.
- `bundled/skills/` stores reviewed first-party Skills without making them
  discoverable before the user selects them.
- `agents/modules/` stores those instruction modules as ordinary Markdown.
- `scripts/codex_kit.py` validates catalogs and safely renders the managed
  global instruction block.
- `tests/test_codex_kit.py` covers catalog and rendering safety boundaries.

## Included instruction modules

| Module | Purpose | Recommended |
| --- | --- | --- |
| `chinese-output-style` | Direct Chinese prose and target-domain technical terminology | Yes |
| `github-markdown-default` | GitHub-compatible defaults for created or substantially revised Markdown | Yes |
| `destructive-operation-confirmation` | Exact impact review and renewed confirmation before destructive actions | Yes |
| `first-principles-review` | Goal, assumption, risk, trade-off, and acceptance-criteria review for substantial requests | No |
| `git-commit-workflow` | Install-time identity privacy check, cautious local commits, and a bilingual fallback format | No |

Recommendations are advisory; installation still requires an explicit user
selection. The machine-dependent `rtk` shell rule is deliberately excluded
from the public catalog.

## Catalog contracts

Every catalog has `schema_version: 2`. Items use stable IDs so a user can make
an unambiguous selection.

A GitHub Skill entry contains:

```json
{
  "id": "example-skill",
  "description": "What the Skill enables and when it is useful.",
  "source": "github",
  "repository": "https://github.com/owner/repository",
  "path": "optional/path/to/skill",
  "scope": "user",
  "recommended": false,
  "notes": "Optional source-specific guidance."
}
```

A bundled Skill entry contains:

```json
{
  "id": "example-skill",
  "description": "What the bundled Skill enables.",
  "source": "bundled",
  "path": "bundled/skills/example-skill",
  "scope": "user",
  "recommended": false,
  "notes": "Optional installation or provenance guidance."
}
```

A plugin entry contains:

```json
{
  "id": "example-plugin",
  "description": "What the plugin enables.",
  "repository": "https://github.com/owner/repository",
  "marketplace": "optional-marketplace-name",
  "plugin": "optional-plugin-name",
  "recommended": false,
  "notes": "Optional source-specific guidance."
}
```

An instruction-module entry contains:

```json
{
  "id": "example-rules",
  "description": "The behavior controlled by this module.",
  "path": "agents/modules/example-rules.md",
  "recommended": false
}
```

`source` accepts `github` or `bundled`. GitHub entries require `repository`;
bundled entries prohibit it and require the exact path
`bundled/skills/<id>`. `scope` accepts `user` or `project` and defaults to
`user`. IDs and plugin identifiers use lowercase kebab-case. Repository fields
accept only complete `https://github.com/owner/repository` URLs. Skill paths
are repository-relative POSIX paths without `..` segments. Instruction paths
must match `agents/modules/*.md`. Unknown fields, duplicate JSON keys, control
characters, unsafe bundled trees, symlinks, and reserved Codex Kit markers are
rejected where applicable.

For a repository containing multiple Skills, omit `path` to register it as a
repository-level source. Selecting that source authorizes read-only discovery.
The installer lists the Skills from the resolved upstream commit and requires
the user to select exact Skill names before preparing an installation command.

## Extending the kit

1. Add one catalog entry with a short description and the upstream GitHub
   repository. Do not copy a transient version number into the catalog.
2. For a first-party Skill, place the complete licensed Skill under
   `bundled/skills/<id>/`, audit it for private or machine-specific content,
   and register it with `source: "bundled"`.
3. For a global instruction module, add its Markdown file under
   `agents/modules/` and register it in `catalog/agents.json`.
4. Validate the repository:

   ```bash
   python3 scripts/codex_kit.py validate --repo .
   python3 -m unittest discover -s tests -v
   ```

5. Review the user-facing choices and installation plan from a clean clone
   before publishing the change.

## Installation model

- Third-party repositories are read at installation time from their current
  default branch.
- Repository-level Skill sources are expanded at installation time. Their
  changing upstream inventory is not copied into this repository.
- Bundled Skills are installed from the exact checked-out Codex Kit tree. They
  do not require a second network source and remain inactive until selected.
- Each installation run resolves the latest default-branch commit, reviews that
  exact tree, and binds the approved transaction to the reviewed commit or
  content digest. A later run resolves the latest commit again; the catalog
  does not carry a permanent version pin.
- An installer must consume that exact commit or a verified local snapshot.
  Installation stops when an upstream tool can only fetch and execute a
  mutable branch without an exact-source option.
- Installer tools requested through `latest` aliases are resolved to a concrete
  tool version before the command is approved.
- Standalone Skills use the upstream installer, Codex `$skill-installer`, or
  a reviewed concrete version of the Vercel Skills CLI as appropriate.
- Full plugins use Codex's native plugin marketplace commands so bundled MCP
  configuration, hooks, and assets remain intact.
- Selected instruction modules are rendered into a marked block in
  `$CODEX_HOME/AGENTS.md`. Codex currently does not expand `@include`
  directives, so the module contents are written into the block.
- Selecting `git-commit-workflow` starts a Git identity privacy check. The
  installer asks about the author name and email separately, offers a
  user-verified GitHub `noreply` address, and defaults to repository-local
  configuration when a target repository is available. It shows the exact
  write, resulting identity, and recovery command before applying a change.

## Safety model

- Opening the repository never starts installation.
- Remote commands and target paths are shown before execution.
- Unmanaged files and same-name installations are not overwritten silently.
- Global instruction changes are backed up and previewed.
- Catalog validation and global instruction rendering use a deterministic
  standard-library helper with strict path, marker, file-type, and atomic-write
  checks.
- The helper preserves existing POSIX mode bits. It atomically refuses to
  overwrite a target that appeared after a missing-file preview. For an
  existing target, keep other editors closed during the short final
  digest-check and atomic-replacement interval.
- A new Codex process checks the effective global instructions after
  installation. Severe conflicts prevent a successful completion report.
- Local selections, paths, commits, and backup locations may be recorded in
  `.codex-kit.local.json`, which Git ignores.
- Git identity values are never stored in the repository or local installation
  receipt.
- System-level operations, secrets, `sudo`, and remote-script pipelines require
  separate explicit approval.

## License

Codex Kit and its bundled first-party content are available under the
[MIT License](LICENSE). Linked third-party repositories retain their own
licenses and are reviewed separately at installation time.

## References

- [Agent Skills specification](https://agentskills.io/specification)
- [Build Skills for Codex](https://learn.chatgpt.com/docs/build-skills)
- [Build Codex plugins](https://developers.openai.com/plugins/build/plugins)
- [Codex `AGENTS.md` behavior](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [GitHub Flavored Markdown specification](https://github.github.com/gfm/)
- [GitHub mathematical expressions](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/writing-mathematical-expressions)
- [`vercel-labs/skills`](https://github.com/vercel-labs/skills)
- [`mattpocock/skills`](https://github.com/mattpocock/skills)
