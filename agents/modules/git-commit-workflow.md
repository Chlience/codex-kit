# Git commit workflow

## Define coherent commit boundaries

- Make each commit one change that can be understood, verified, and reverted
  independently. Include the implementation, focused tests, and necessary
  documentation for that change in the same commit.
- Keep dependent work in a continuous, reviewable order. Do not combine
  non-adjacent steps such as A and C while leaving the required intermediate
  step B for another commit.
- Separate unrelated features, fixes, refactors, tests, documentation, and
  infrastructure changes when each has its own purpose or rollback boundary.
- Split large work into the smallest complete sequence whose intermediate
  commits preserve required behavior and pass their relevant verification.
- After completing and verifying repository changes, create focused local
  commits by default when repository instructions allow it. Follow a different
  delivery workflow when the user explicitly requests one.

## Check identity, staged content, and verification

- Use the repository's configured Git identity, falling back to the existing
  global Git identity. Do not change identity settings unless the user asks.
- If the effective author name or email is missing, stop before committing and
  ask the user to configure it. Never invent identity values.
- Before every commit, inspect the staged diff. Stage only files or hunks that
  belong to the current change, and preserve unrelated user changes.
- Run the smallest verification that covers the commit's observable behavior,
  public interfaces, failure paths, and relevant compatibility constraints.
- Do not create a commit while its required verification is failing. If a
  check cannot run, record the exact unverified item and reason.

## Write the commit message

Repository contribution requirements and explicit user instructions take
precedence. Otherwise, use a suitable Conventional Commit type such as `feat`,
`fix`, `docs`, `test`, `refactor`, or `chore`. Add a concise scope when it helps
identify the affected capability. Use this structure:

```text
<type>(<optional-scope>): <English one-sentence summary>

<problem background: why the change is needed and the observable outcome>

<implementation: the behavior or capability added or changed>

Boundary: <what is included, what remains outside, and which behavior is preserved>

Validation: <specific evidence from checks actually run and exact unverified items>
```

Omit the scope and parentheses when no useful scope exists. Keep the summary
concise and scoped to the same change. The body is required by default and has
exactly four paragraphs:

1. Explain why the change is needed and state the observable outcome.
2. Explain the behavior or capability added or modified. Describe functional
   effects instead of listing files.
3. Start with `Boundary:` and state what the commit includes, excludes, and
   intentionally preserves.
4. Start with `Validation:` and report specific observed evidence, such as
   covered behavior, rejected invalid inputs, compatibility checks, or measured
   results.

Record only checks that actually ran and their observed results. Do not use a
generic statement such as “tests passed” without naming what the checks cover.
If a required check could not run, name the exact unverified item and reason.

Do not add generated attribution, co-author trailers, Lore-style trailers, or
additional body sections unless repository rules or the user require them.

Example:

```text
feat(swe-smith): build runtime task assets

Runtime needs one trusted contract that joins pinned task data with
verified image observations.

Build typed SWE-Smith task assets and a JSONL registry from private
source specifications and image probes.

Boundary: This is a pure local join with no platform calls or
sandbox startup.

Validation: Tests cover reloadable assets and rejection of
inconsistent source data and image digests.
```

## Control pushing and history rewrites

- Do not push unless the user explicitly asks.
- Amend, squash, rebase, reorder, or otherwise rewrite history automatically
  only when every affected commit was created by the agent during the current
  task, remains unpushed, and has no user-created or unknown-provenance
  descendant whose hash would also change.
- Other history rewrites require user confirmation for the exact commit range,
  affected references, impact, and recovery path.
- Rewriting pushed commits, force pushing, hard resets, and deleting branches,
  tags, or references always require renewed confirmation for the exact target
  and recovery procedure.

## Report commit evidence

After each commit, report:

- the commit identifier and delivered behavior;
- the minimal verification that passed;
- compatibility behavior intentionally preserved;
- remaining work and any unverified items.
