# Engineering change discipline

Apply these rules to features, bug fixes, refactors, performance work, and
infrastructure changes.

## Confirm assumptions and outcomes

Before substantial implementation, establish the observable outcome, scope,
exclusions, preserved behavior, hard constraints, and verification method.
Identify assumptions that could affect:

- user-visible behavior and business rules;
- data meaning, ownership, storage, or migration;
- public interfaces, compatibility, or system boundaries;
- security, permissions, performance, or operating scale;
- external dependencies or future iteration paths.

Treat an assumption as confirmed only when the user states it or designates an
authoritative project artifact as its source of truth. Do not infer
consequential requirements from names, conventions, vague goals such as
"extensible", or personal preference.

For an unresolved consequential assumption, state its impact and ask for the
smallest decision needed. Do not implement the affected choice before
confirmation. Local, reversible details that preserve external behavior may
follow project conventions. Treat confirmed assumptions as constraints and
reconfirm material changes.

## Make the smallest justified change

Rank priorities in this order:

1. correctness, data integrity, security, and compatibility;
2. applicable performance and resource constraints;
3. the confirmed product or engineering outcome;
4. maintainability, reviewability, and scope control;
5. delivery time.

A failed hard constraint leaves the work incomplete. Deliver the smallest
complete path, including necessary failure handling, tests, and documentation;
record adjacent improvements as follow-ups. Confirm material scope expansion or
an unplanned public interface, data model, dependency, or architecture choice
with the user.

Each new abstraction, dependency, or infrastructure component must serve a
confirmed need or concrete change scenario and remove duplicated decisions,
isolate known variation, reduce change sites, or supply required capability.
Defer speculative generality. Treat coverage, code volume, and speed as
supporting signals only.

## Validate stable contracts

Test stable contracts first: observable behavior, public interfaces,
integration boundaries, failure paths, and relevant performance or security
properties. Test internals directly only when they have stable, independent
semantics. Avoid tests that freeze temporary implementation structure.

Split large changes into independently verifiable and reviewable stages. After
each stage, check behavior, tests, relevant metrics, scope growth, and added
complexity. Pause and replan when regressions appear, assumptions change, or
the change grows materially beyond its expected boundary.

Close with evidence: confirmed assumptions, delivered behavior, preserved
contracts, verification results, relevant measurements, known limitations,
unverified items, and follow-ups. Mark work complete only when evidence satisfies
the confirmed acceptance criteria.
