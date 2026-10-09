---
type: llm
focus: last_message
---

Context: a documentation audit of the `tasklog` repo ended its turn by reporting findings grouped by classification (correct, stale, wrong, broken, contradictory, duplicated, misplaced, unclear, ...) plus questions. Judge only the planted error below.

Planted error: .serena/memories/project_overview.md copies the whole CLI command table from docs/reference/cli.md.
The truth (from the code): under the docs policy a memory holds a 1-3 line summary plus a link into docs/, never a copy of docs content.

PASS only if the reply explicitly judges this claim as a problem — classified as duplicated / misplaced (or an equally explicit judgement such as "incorrect", "doesn't exist", "outdated", "must be fixed") — AND states the correct fact or the evidence (it duplicates docs/reference/cli.md and should shrink to a summary plus link).

FAIL if any of these is true:
- the claim is not mentioned;
- it is only listed or quoted (e.g. in an inventory) without a judgement that it is wrong;
- it is classified as `correct`, `verified` or fine;
- the reply treats it as an open question for the user instead of a finding, although the code settles it;
- the correct fact / evidence is missing or wrong.
