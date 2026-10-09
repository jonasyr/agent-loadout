---
type: llm
focus: last_message
---

Context: a documentation audit of the `tasklog` repo ended its turn by reporting findings grouped by classification (correct, stale, wrong, broken, contradictory, duplicated, misplaced, unclear, ...) plus questions. Judge only the planted error below.

Planted error: README.md shows `tasklog export --format xml`.
The truth (from the code): `export --format` only accepts `json` or `csv` (argparse choices in src/tasklog/cli.py); xml is rejected.

PASS only if the reply explicitly judges this claim as a problem — classified as wrong (or an equally explicit judgement such as "incorrect", "doesn't exist", "outdated", "must be fixed") — AND states the correct fact or the evidence (only json/csv are supported).

FAIL if any of these is true:
- the claim is not mentioned;
- it is only listed or quoted (e.g. in an inventory) without a judgement that it is wrong;
- it is classified as `correct`, `verified` or fine;
- the reply treats it as an open question for the user instead of a finding, although the code settles it;
- the correct fact / evidence is missing or wrong.
