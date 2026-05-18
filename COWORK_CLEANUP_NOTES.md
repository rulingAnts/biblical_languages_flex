# Cowork Cleanup Notes — 2026-05-18

This file was written during a Cowork session (Seth + Claude) that ran a
sync/cleanup pass across `~/GIT/`. It's a hand-off note for the next
human or AI that touches this repo.

## What was done

- Added `.claude/` and `.DS_Store` to `.gitignore` so the Claude Code
  workspace state and macOS metadata files stop showing up as untracked.
- Committed `tools/Morph_Prototype.py` (was untracked before the session).

## Caveat — initial `.gitignore` was malformed

The first append into `.gitignore` from the sandbox happened without a
trailing newline on the existing file, so two entries got concatenated:

```
tools/dev-server.js.claude/
```

…instead of two separate lines:

```
tools/dev-server.js
.claude/
```

This was fixed by a follow-up commit ("Fix .gitignore: separate
dev-server.js and .claude/ entries"). If you see only the broken line in
history, check whether the fix-up commit is also present.

## What was deliberately not done

- Nothing else. The repo should be clean after the fix-up commit.
