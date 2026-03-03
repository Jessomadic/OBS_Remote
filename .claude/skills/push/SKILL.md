---
name: push
description: Stage all changes, write a commit message, and push to GitHub main branch
argument-hint: "[optional commit message]"
allowed-tools: Bash(git *)
---

Stage, commit, and push all current changes to the `main` branch of the OBS Remote repo at https://github.com/Jessomadic/OBS_Remote.

**Steps:**
1. Run `git status` to show what has changed
2. Run `git diff --stat` to summarise the diff
3. Determine a clear, concise commit message that explains *why* these changes were made (not just what). If $ARGUMENTS is non-empty, use that as the commit message instead.
4. Stage all changed files with `git add` (be selective — never stage .env or secrets)
5. Commit using the message (pass via heredoc to preserve formatting):
   ```
   git commit -m "$(cat <<'EOF'
   <your message here>

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```
6. Push to `origin main`
7. Report the commit hash and confirm the push succeeded

If there is nothing to commit, say so clearly and stop.
Do not amend existing commits. Always create a new commit.
