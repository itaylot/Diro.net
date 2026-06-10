# Fix Bug

Bug description: $ARGUMENTS

## Process

1. **Understand first** — restate the bug in your own words before touching anything
2. **Find the cause** — read only the files likely to contain the bug:
   - Check `CLAUDE.md` for relevant architecture notes
   - Read only the specific file(s) related to the bug
   - Do NOT scan the whole project
3. **Propose the fix** — describe what you'll change and why, before editing
4. **Make the smallest safe change** — fix only what's broken
   - Do not refactor surrounding code
   - Do not rename variables or reorganize logic
   - Do not fix unrelated issues you notice
5. **Verify** — confirm the fix addresses the described bug
6. **Report** — state clearly:
   - What the root cause was
   - What line(s) changed
   - What to test to confirm it's fixed

## Rules
- If the bug description is unclear, ask one clarifying question before proceeding
- If the fix requires changing more than ~20 lines, flag it and ask for confirmation
- If you're uncertain about the cause, say so explicitly
