# Tasklog Export Formats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eight new export formats for `tasklog export --format`.

**Architecture:** `src/tasklog/exporters/__init__.py` already discovers every module in the package; each module defines `NAME` and `render(tasks) -> str` and nothing else. The eight tasks are fully independent: each creates exactly one module and one test file, shares no code with the others, and touches no existing file. Exports only read tasks; nothing writes to the user's database. The formats need care with escaping and edge cases, so the plan gives the requirements and tests to write, not the code.

**Tech Stack:** Python 3.11 stdlib only, pytest.

---

### Task 1: Markdown table exporter

**Files:**
- Create: `src/tasklog/exporters/markdown.py` (`NAME = "markdown"`)
- Test: `tests/test_export_markdown.py`

Output: a GitHub-flavoured Markdown table with columns `#`, `Title`, `Created` (ISO date), `Archived` (`yes`/`no`); pipes and newlines in titles must be escaped so the table never breaks.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_markdown.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): markdown format`

### Task 2: HTML page exporter

**Files:**
- Create: `src/tasklog/exporters/html.py` (`NAME = "html"`)
- Test: `tests/test_export_html.py`

Output: a standalone HTML5 page with a `<table>`; every title is HTML-escaped; archived rows get `class="archived"`; no external assets.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_html.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): html format`

### Task 3: iCalendar exporter

**Files:**
- Create: `src/tasklog/exporters/ics.py` (`NAME = "ics"`)
- Test: `tests/test_export_ics.py`

Output: an RFC 5545 calendar with one `VTODO` per task (`UID` = `tasklog-<id>@local`, `SUMMARY`, `DTSTAMP` from `created` in UTC, `STATUS:COMPLETED` for archived tasks); lines are folded at 75 octets and text values escaped per the RFC.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_ics.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): ics format`

### Task 4: todo.txt exporter

**Files:**
- Create: `src/tasklog/exporters/todotxt.py` (`NAME = "todotxt"`)
- Test: `tests/test_export_todotxt.py`

Output: one line per task in todo.txt format: `x ` prefix for archived tasks, the creation date as `YYYY-MM-DD`, then the title; titles that start with `x ` or a date must not be misread as such.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_todotxt.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): todotxt format`

### Task 5: Org mode exporter

**Files:**
- Create: `src/tasklog/exporters/org.py` (`NAME = "org"`)
- Test: `tests/test_export_org.py`

Output: an Org-mode file with one `* TODO` / `* DONE` heading per task and a `:PROPERTIES:` drawer holding `ID` and `CREATED` (`[YYYY-MM-DD Day HH:MM]`); titles containing `*` at the start or `:tags:` at the end are escaped.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_org.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): org format`

### Task 6: NDJSON exporter

**Files:**
- Create: `src/tasklog/exporters/ndjson.py` (`NAME = "ndjson"`)
- Test: `tests/test_export_ndjson.py`

Output: one compact JSON object per line (`id`, `title`, `created` as ISO 8601 UTC, `archived`), UTF-8, no trailing comma or array; must round-trip through `json.loads` line by line.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_ndjson.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): ndjson format`

### Task 7: XML exporter

**Files:**
- Create: `src/tasklog/exporters/xml.py` (`NAME = "xml"`)
- Test: `tests/test_export_xml.py`

Output: an XML document `<tasks version="1">` with one `<task id="…" archived="true|false">` per task, the title as text and `created` as an attribute; built with `xml.etree.ElementTree` so escaping is correct, and documented by a small XSD in `docs/tasks.xsd`.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_xml.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): xml format`

### Task 8: TSV exporter

**Files:**
- Create: `src/tasklog/exporters/tsv.py` (`NAME = "tsv"`)
- Test: `tests/test_export_tsv.py`

Output: tab-separated values with a header line; tabs, newlines and backslashes inside titles are escaped as `\t`, `\n`, `\\` so every task stays on one line, and a matching `parse_tsv` helper for the tests proves the round trip.

- [ ] **Step 1: Write failing tests** for the format, an empty task list, a title with every character the format must escape, a non-ASCII title, and an archived task
- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `render`** to the requirements above (stdlib only)
- [ ] **Step 4: Run `pytest tests/test_export_tsv.py -q`**, then the whole suite
- [ ] **Step 5: Commit** `feat(export): tsv format`
