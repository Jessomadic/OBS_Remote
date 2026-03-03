---
name: audit
description: Run a full code audit of the OBS Remote project — security, quality, and correctness review
argument-hint: "[optional: specific file or area to focus on]"
allowed-tools: Read, Grep, Glob
---

Perform a thorough code audit of the OBS Remote project at `D:/Coding/OBS Remote`.

If $ARGUMENTS is non-empty, focus the audit on that file, directory, or area. Otherwise audit the full project.

**Audit checklist:**

### 1. Security
- Look for any hardcoded secrets, passwords, or API keys in source files
- Check that no sensitive config (obs_password, etc.) is logged or exposed in API responses
- Verify CORS policy in `server/main.py` — is `allow_origins=["*"]` acceptable for local-only use?
- Check for command injection risk in `server/updater.py` (subprocess calls with user-controlled data)
- Review any `os.system` / `subprocess` calls for injection risk

### 2. Error handling
- Ensure every OBS route handles disconnection gracefully (returns 503, not 500)
- Check that the WebSocket bridge never crashes the server on bad OBS events
- Verify the updater handles partial downloads and bad checksums

### 3. Code quality
- Flag any duplicate logic across route modules
- Check that `obs_client.py` thread-safety is adequate (concurrent HTTP requests + event thread)
- Verify config reads/writes are atomic enough for concurrent access

### 4. Correctness
- Confirm obsws-python method names match actual obs-websocket v5 API
- Check that volume dB range (-100 to 26) is enforced in the audio slider
- Verify the Inno Setup script properly handles upgrades (stops old service before replacing files)

### 5. Dependencies
- Flag any pinned package versions in `requirements.txt` that have known CVEs
- Check if `obsws-python==1.7.0` is still the latest stable release

**Output format:**
For each finding, state:
- **Severity**: Critical / High / Medium / Low / Info
- **File + line**: where the issue is
- **Issue**: what the problem is
- **Recommendation**: how to fix it

End with an overall summary and a prioritised fix list.
