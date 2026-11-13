---
name: ship-develop
description: Ship a finished develop branch to main. Squash-merge develop into main as one commit, reset develop to main, and, once the repo uses tags, create a SemVer tag (and a release once a release pipeline exists). Use only when Ben asks to ship, release, or merge develop into main ("develop ist fertig", "nach main mergen", "release machen", /ship-develop).
---

# Ship develop to main

Runs the release step from the Git workflow in `CLAUDE.md`. Talk to Ben in German; PR titles, PR bodies, and commit titles are in English.

## Hard rules

- **Always ask before executing.** Ben cannot read the PR before it is merged, so the confirmation in step 2 replaces his review. Nothing is created, merged, tagged, or force-pushed before he says yes.
- Never delete `develop`. Never force-push `main`.
- Commit, tag, and PR authorship follow `CLAUDE.md` (Ben is author, Claude is co-author).

## 1. Check the state (read-only)

```bash
git fetch --prune --tags origin
git log --oneline origin/main..origin/develop    # what ships
git diff --stat origin/main origin/develop       # files changed
git tag --sort=-v:refname | head -5              # existing tags
ls .github/workflows/                            # look for a release pipeline
```

- If `develop` has no commits ahead of `main`, or the diff is empty, stop and tell Ben there is nothing to ship.
- CI only runs on the `develop` → `main` PR and on pushes to `main`, so there is no CI result for `develop` yet; it is checked in step 3.
- **Tags are active** when `git tag` lists at least one tag.
- **A release pipeline exists** when a workflow in `.github/workflows/` runs on tag pushes (`on: push: tags:`).

## 2. Ask Ben (AskUserQuestion)

Show a short summary in German:
- the commits that will ship, and the changed files
- the proposed squash commit title, in English, with the type prefix like every PR title (`Feature: Plugin system`, `Fix: Crash on empty library`; types in `CLAUDE.md`); GitHub appends the PR number
- **when tags are active:** a proposed tag, plus the alternatives, from the latest tag using SemVer:
  - breaking change (removed feature, incompatible data format or config) → MAJOR
  - new feature → MINOR
  - bugfixes, docs, refactoring only → PATCH
  - while the version is below `v1.0.0`, propose MINOR for breaking changes too, and say so
- **when a release pipeline exists:** that pushing the tag will publish a GitHub release

Options: proceed as proposed, a different tag, or cancel. Without a clear yes, stop.

## 3. Squash-merge into main

1. Create a PR `develop` → `main`. Title is the squash commit title. The body summarises what ships and ends with the attribution lines from `CLAUDE.md`.
2. Wait for the CI check on that PR. If it is red, stop and report it; do not merge.
3. Merge it. GitHub squashes automatically and uses the PR title as commit message, so the title must be final when the PR is created. Set `expectedHeadSha` to the full SHA of `origin/develop` and pass the `Co-Authored-By` trailer as `commit_message`, so Claude stays co-author.
4. Fetch and confirm `origin/main` gained exactly one new commit.

## 4. Reset develop

```bash
git fetch --prune origin
git checkout develop
git reset --hard origin/main
git push --force-with-lease=develop:<old develop SHA> origin develop
git rev-list --left-right --count origin/main...origin/develop   # must print 0  0
```

GitHub deletes head branches after a merge and `develop` is the head of this PR, so expect it to be gone: push it again from the local copy (`git push -u origin develop`) and tell Ben.

## 5. Tag (only when tags are active and Ben confirmed a tag)

```bash
git checkout main && git pull origin main
git -c user.name="Ben Waibel" -c user.email="103282803+NEXT876@users.noreply.github.com" \
  tag -a vX.Y.Z -m "vX.Y.Z: <squash commit title>"
git push origin vX.Y.Z
git checkout develop
```

If no tags exist yet, skip this step and mention that the first tag has to be set once by hand (or on Ben's request).

## 6. Release (only when a release pipeline exists)

Pushing the tag triggers the pipeline. Check the workflow run for the tag, and report the release link once it succeeds or the error if it fails. Every tag must lead to a release: if the run fails, say so clearly and do not create a new tag to retry.

If there is no release pipeline yet, skip this step.

## 7. Report

Summarise in German: PR link, the new commit on `main`, `develop` reset (0 / 0), and the tag and release (or why they were skipped).
