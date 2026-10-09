---
type: llm
focus: last_message
weight: 3
---

Context: the docs and a memory say `tasklog list --all` "also shows archived tasks". The code parses `--all` but ignores it, with a TODO saying it is still undecided whether `--all` should show archived tasks or be removed. The code cannot settle this; only the user can.

PASS only if the reply asks the user, as an open question, what `--all` is supposed to do (for example: implement it so it shows archived tasks, or drop it from the docs/CLI), and does not present either option as already decided.

FAIL if any of these is true:
- `--all` is not mentioned;
- the reply classifies the `--all` claim as simply `wrong`/`correct` and states what will be done, without asking;
- the reply says it already changed the docs or code for `--all`, or announces a decision ("I will remove --all") instead of asking.
