<!--
PRs into develop. Title: "<Type>: <what changes>", in English.
Types: Feature, Fix, Refactor, Docs, Test, Chore.
Example: "Feature: Duel mode with Elo ratings", "Fix: Crash on empty library".
Branch names start with their type: feature/, fix/, refactor/, docs/, test/, chore/.
GitHub squashes on merge (the PR title becomes the commit message) and deletes the branch afterwards.
-->

## Type

<!-- Keep exactly one; it matches the title prefix. -->

- [ ] Feature: new behavior for the user
- [ ] Fix: a bug is fixed
- [ ] Refactor: structure changes, behavior stays the same
- [ ] Docs: documentation only
- [ ] Test: tests only
- [ ] Chore: tooling, CI, dependencies

## Summary

<!-- What changes and why, in a few bullets. -->

-

## Test plan

- [ ] `pytest`
- [ ] `ruff check .`
- [ ] `graphify update .` run and `graphify-out/` committed (code changes)

Co-Authored-By: Claude <noreply@anthropic.com>
