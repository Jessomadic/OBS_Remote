---
name: pull
description: Pull the latest changes from the main branch of the OBS Remote GitHub repo
allowed-tools: Bash(git *)
---

Pull the latest changes from `origin main` for the OBS Remote project.

**Steps:**
1. Run `git status` — if there are uncommitted local changes, warn the user and ask whether to stash them first (stash with `git stash` if needed)
2. Run `git fetch origin`
3. Show what's incoming with `git log HEAD..origin/main --oneline` — if nothing, say "Already up to date" and stop
4. Run `git pull origin main`
5. Show a summary of what changed: files modified, any new files, removed files
6. If a stash was made, pop it with `git stash pop` and report the result

Report any merge conflicts clearly and do not try to auto-resolve them without user confirmation.
