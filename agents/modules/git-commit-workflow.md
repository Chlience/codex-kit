# Git commit workflow

- Use the repository's configured Git identity, falling back to the existing
  global Git identity. Do not change identity settings unless the user asks.
- If the effective author name or email is missing, stop before committing and
  ask the user to configure it. Never invent identity values.
- Do not push unless the user explicitly asks to push.
- After completing and verifying repository changes, the agent may create a
  focused local commit when repository instructions allow it.
- Inspect the staged diff before committing. Stage only files that belong to
  the current task, and preserve unrelated user changes.
- Amend, squash, reorder, or otherwise rewrite history automatically only when
  every commit whose content or hash would change was created by the agent
  during the current task, remains unpushed, and has no user-created or
  unknown-provenance descendant that would also be rewritten.
- Other history rewrites require user confirmation for the exact commit range.
  Force pushes, hard resets, and reference deletion always require a separate
  review of the target, impact, recovery path, and renewed confirmation.

When the repository does not define its own commit format, use exactly:

```text
<type>: English one-sentence summary

<type>: 中文一句话总结
```

Use a suitable Conventional Commit type such as `feat`, `fix`, `docs`,
`chore`, `refactor`, `test`, or `style`. Keep each summary concise and scoped
to the same change.

Repository contribution requirements take precedence, including required
issue identifiers, signing, DCO sign-off, trailers, bodies, or language
conventions. Otherwise, do not add co-author trailers, generated attribution,
or extra commit bodies unless the user asks.
