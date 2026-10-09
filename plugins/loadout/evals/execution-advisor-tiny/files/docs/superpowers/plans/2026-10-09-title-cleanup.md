# Title Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip surrounding whitespace from task titles, and make `tasklog list --all` show archived tasks.

**Architecture:** Two small edits in the existing modules; no new files besides tests.

**Tech Stack:** Python 3.11, pytest.

---

### Task 1: Strip whitespace from titles

**Files:**
- Modify: `src/tasklog/store.py` (`Store.add`)
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_store.py`:

```python
def test_add_strips_whitespace(tmp_path):
    store = Store(tmp_path / "t.db")
    assert store.add("  buy milk  ").title == "buy milk"
```

- [ ] **Step 2: Run it and see it fail**

Run: `pytest tests/test_store.py::test_add_strips_whitespace -q`
Expected: FAIL (`'  buy milk  ' != 'buy milk'`)

- [ ] **Step 3: Implement**

In `Store.add`, make this the first line of the method body:

```python
        title = title.strip()
```

- [ ] **Step 4: Run the tests**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git commit -am "fix(store): strip whitespace from task titles"
```

### Task 2: `list --all` shows archived tasks

**Files:**
- Modify: `src/tasklog/cli.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_store.py`:

```python
from tasklog.cli import main


def test_list_all_shows_archived(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASKLOG_HOME", str(tmp_path))
    main(["add", "old"])
    main(["archive", "1"])
    main(["list", "--all"])
    assert "#1 old" in capsys.readouterr().out
```

- [ ] **Step 2: Run it and see it fail**

Run: `pytest tests/test_store.py::test_list_all_shows_archived -q`
Expected: FAIL (`#1 old` not in output)

- [ ] **Step 3: Implement**

In `src/tasklog/cli.py` replace the `--all` argument and the `list` branch:

```python
    ls.add_argument("--all", action="store_true", help="also show archived tasks")
```

```python
    elif args.command == "list":
        for t in store.list(include_archived=args.all):
            print(f"#{t.id} {t.title}")
```

Delete the `# TODO: decide whether --all ...` comment above the argument.

- [ ] **Step 4: Run the tests**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(cli): list --all shows archived tasks"
```
