---
name: code-review
description: Reviews a code change for bugs, style, security, and performance issues, then issues a PASS or REJECT verdict.
version: 1.0.0
triggers:
  - code review
  - review pr
  - check code quality
---

# Code Review

When invoked, follow this checklist on every file passed in:

1. **Bugs** — wrong logic, off-by-one, null derefs, race conditions.
2. **Style** — naming, formatting, idioms appropriate to the language.
3. **Security** — injection, hard-coded secrets, unvalidated input.
4. **Performance** — obvious O(n²) inside a hot loop, unnecessary I/O.

Output one block per file as `path:line — CATEGORY: message`. End with one of:

- `PASS` — no blocking issues.
- `REJECT` — at least one BUG or SECURITY finding.

If you cannot read a file, say so explicitly; do not invent issues.
