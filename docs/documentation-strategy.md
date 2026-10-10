# Documentation strategy

How agent-loadout wants a repository's documentation to look, why, and how the kit keeps it that way. Read this if you are deciding whether to adopt the approach in your own repos.

**In one sentence:** every fact has exactly one home, `docs/` is that home, and everything else (README, AGENTS.md, agent memories) is a short entry point that links into it.

## The problem

Look at almost any repo that has had a few months of human and agent work:

- The README explains installation, architecture, every CLI flag and a roadmap, and half of it is out of date.
- `CLAUDE.md` has grown to 300 lines because every session added "one more important rule".
- `docs/notes.md` holds the real decisions, mixed with to-dos.
- `docs/api.md` describes an endpoint that was renamed two releases ago.
- The agent's memories copy the README and disagree with it on a default value.

None of these files is wrong on purpose. Each one started as a reasonable copy of a fact, and copies drift apart. Research on documentation problems puts this at the centre: in a taxonomy built from 878 real documentation-related artifacts (mailing lists, Stack Overflow, issues, pull requests), problems with the *content itself* (correctness, completeness, up-to-dateness) were the largest category, discussed in 55% of the artifacts [Aghajani 2019; 2020].

With coding agents the cost goes up:

- **Agents read everything you load into their context, on every task.** A bloated instruction file costs tokens and attention in every session, and long contexts are used unevenly: models find information at the start or end of a long input more reliably than in the middle [Liu 2024], and their reliability drops as input grows [Hong 2025].
- **Contradictions are resolved at random.** Claude Code's own documentation warns that when two instructions contradict each other, "Claude may pick one arbitrarily" [Claude Code memory docs].
- **Decisions get lost.** The code shows *what* was built, not *why*. When the reasons live only in a chat or someone's head, the next person (or agent) either keeps a choice blindly or reverses it blindly. Nygard named both failure modes in 2011 [Nygard 2011]; the architecture literature calls the loss "knowledge vaporization" [Jansen & Bosch 2005, as cited by Shahbazian 2017].

## The model: one home per fact

The fix is old and boring: treat documentation like code. Write it in plain text, keep it in version control next to the code, review it in pull requests, and test it [Write the Docs]. Then add one rule on top: **a fact lives in one place; every other place links to it.**

| Layer | Holds | Rule |
|---|---|---|
| `README.md` | What the project is, how to install and run it | Human entry point; links into `docs/` |
| `docs/` | Everything a human may need: concepts, architecture, how-tos, reference; decisions as ADRs in `docs/adr/` | Single source of truth |
| `AGENTS.md` (plus `CLAUDE.md` containing only `@AGENTS.md`) | Purpose, commands, hard conventions, a map of `docs/` and memories | Short and hand-curated; never copies docs content |
| `.serena/memories/` (committed) | Agent working notes: per topic a 1–3 line summary plus a link into `docs/`; gotchas; "to do X, touch these files"; current status | Never the only home of a fact a human would need |
| Claude Code auto memory (`~/.claude/projects/…`) | Temporary or machine-specific notes | Never project facts; it is machine-local and not shared |

This is the kit's [docs policy](../rules/docs-policy.md) and [memory policy](../rules/memory-policy.md); both are loaded into every Claude Code session on a machine set up with loadout.

Two details matter:

- **`CLAUDE.md` is one line: `@AGENTS.md`.** AGENTS.md is an open format read by many agents (Codex, Cursor, Gemini CLI, GitHub Copilot's coding agent, Aider and others) [agents.md]. Claude Code expands `@path` imports in CLAUDE.md [Claude Code memory docs], so one file serves every agent, and nothing has to be kept in sync.
- **Memories are an index, not a second wiki.** A memory says "export formats and defaults: see `docs/reference/cli.md`", not a copy of the table. When the table changes, the memory is still right.

## Diátaxis: four kinds of docs

Inside `docs/`, the kit follows Diátaxis where it fits. Diátaxis, by Daniele Procida, sorts documentation by the reader's need along two axes [Diátaxis]:

- **action or cognition:** is the reader doing something, or trying to know something?
- **acquisition or application:** are they studying, or at work?

| | Acquisition (study) | Application (work) |
|---|---|---|
| **Action** | **Tutorial:** a guided lesson that gets a beginner to a first success | **How-to guide:** steps to reach a specific goal |
| **Cognition** | **Explanation:** background, design, the why | **Reference:** exact facts to look up |

Mixing the types is what makes docs hard to use. A tutorial that stops to list every option loses the learner; a reference page that tells a story cannot be scanned; a how-to that explains the architecture buries the steps.

Examples from two kinds of projects:

| Type | RAG / ML research project | Web app |
|---|---|---|
| Tutorial | Run your first chunking experiment end to end | Build and run the app locally, add your first page |
| How-to | Add a new chunking strategy; rerun the evaluation on a new dataset | Add an API endpoint; rotate the session secret |
| Reference | Config keys and defaults; metric definitions; dataset schema | Endpoints, environment variables, CLI scripts |
| Explanation | Why fixed-size chunks underperform here; how the evaluation avoids leakage | How auth and sessions work; why state lives on the server |

Diátaxis is a guide, not a template. **A small repo creates only the types it has content for.** A 500-line CLI may need nothing but `docs/reference/` and one ADR. Empty folders help nobody.

Canonical adopted Diátaxis across its technical documentation [Canonical 2021]; the Diátaxis site carries testimonials from teams at Gatsby, Cloudflare and Vonage [Diátaxis].

## ADRs: decisions with their reasons

An Architecture Decision Record captures one significant decision, its context and its consequences [adr.github.io]. The kit uses Michael Nygard's lightweight format [Nygard 2011]:

- **Context:** the forces at play, stated as facts, including the ones in tension.
- **Decision:** what we will do, in full sentences ("We will …").
- **Consequences:** what follows, good, bad and neutral.
- **Status:** proposed, accepted, deprecated or superseded.

Three rules make ADRs work:

1. **Numbered and never renumbered.** `docs/adr/0001-short-title.md`, `0002-…`.
2. **Immutable once accepted.** When a decision changes, write a new ADR and mark the old one "superseded by 0007". As Nygard puts it, the old decision stays relevant because it *was* the decision.
3. **Small.** "Large documents are never kept up to date. Small, modular documents have at least a chance at being updated." [Nygard 2011]

A realistic example:

```markdown
# 0003. Chunk by sentence windows instead of fixed token counts

## Status
Accepted (supersedes 0001)

## Context
Fixed 512-token chunks split sentences and tables. On our evaluation set, answers
often needed text that sat across a chunk boundary. The embedding model accepts
up to 512 tokens; the index must be rebuilt for any chunking change.

## Decision
We will chunk by windows of whole sentences (target 300 tokens, 1 sentence overlap),
keeping tables as single chunks.

## Consequences
- Fewer answers that need two chunks; chunk sizes now vary.
- The index has to be rebuilt once; old experiment results are not comparable.
- Tables longer than 512 tokens still need a separate rule (open).
```

Why it matters: for humans, an ADR answers "why on earth is it like this?" in a minute instead of an afternoon of `git blame`. For agents, it is the difference between "this looks odd, let me clean it up" and "this was decided on purpose, see ADR 0003". Thoughtworks put lightweight ADRs in the "Adopt" ring of its Technology Radar and prefers keeping them in source control over a wiki [Thoughtworks 2018].

## Why this suits coding agents

- **Lean always-loaded context.** AGENTS.md is loaded into every session, so it should hold only what is needed on every task: commands, hard conventions, a map. Anthropic's guidance for agents is "the smallest possible set of high-signal tokens", and Claude Code's docs recommend keeping each CLAUDE.md under 200 lines, because longer files cost context and reduce adherence [Anthropic 2025; Claude Code memory docs].
- **Details on demand.** The map tells the agent where the facts are, and it reads the one page it needs, when it needs it. This is the "just in time" pattern Anthropic describes: keep lightweight identifiers such as file paths and load the data with tools at runtime [Anthropic 2025].
- **Verifiable claims.** A fact with one home can be checked against the code once and fixed once. A fact with five copies cannot.
- **Agent-neutral.** AGENTS.md works with the agents listed above; nothing about the structure is tied to Claude Code. (loadout's skills that maintain it run in Claude Code.)

The evidence on context files themselves is mixed, which is exactly why the kit keeps AGENTS.md small. One 2026 study found that context files, both LLM-generated and developer-written, did not generally improve task success, raised inference cost by over 20%, and that repository overviews in particular did not help; agents did follow the instructions, and the files were useful for specifying non-standard practices [Gloaguen 2026]. Another found that an AGENTS.md was associated with 28.64% lower median runtime and 16.58% fewer output tokens with comparable task completion [Lulla 2026]. Both are preprints. The common thread: a short file with the non-obvious commands and conventions earns its place; a long overview mostly costs tokens.

## How the kit keeps it true

Writing good docs once is the easy part. loadout ships three Claude Code skills for keeping them right:

| Skill | When | What it does |
|---|---|---|
| `/loadout:onboard` | After `loadout init`, or when a repo has no AGENTS.md | **New repo:** asks purpose, users, stack and constraints one at a time, then writes AGENTS.md, `docs/README.md` and `docs/adr/0001-<stack-decision>.md`. **Existing repo:** indexes the code, finds the install/test/run commands and verifies each with a harmless form (`--help`, `--collect-only`, dry run), writes or repairs AGENTS.md, offers to move CLAUDE.md content into AGENTS.md, and writes Serena memories as summary plus link. If docs or memories already exist, it recommends a docs audit. |
| `/loadout:docs-sync` | End of every feature, before merging | Reads the branch diff, decides which facts changed and which layer owns each, updates only those (a new decision becomes an ADR), checks every link and path it touched, and commits separately as `docs: …` after approval. A small change usually touches zero or one doc file; if it finds widespread rot, it stops and recommends an audit. |
| `/loadout:docs-audit` | On request, when docs may be stale or duplicated | Inventories every doc artifact, extracts each claim (commands, paths, symbols, defaults, behaviour, decisions, status), verifies it against the current code, and classifies it: correct, stale, wrong, unclear, contradictory, duplicated, misplaced or unverifiable. It also lists what is missing. Anything the code cannot settle it asks you, in batches; it never guesses intent. It proposes the target structure before rewriting, validates every link afterwards, and commits per layer after approval. Its checklist lives in `.loadout/docs-audit/<date>.md`, so it can resume after a context reset or in a new session. |

The audit is deliberately thorough and expensive; it runs only when you invoke it. docs-sync is the cheap habit that makes audits rare.

### Before and after: a typical repo

```text
Before                                   After
├── README.md        (install, arch,     ├── README.md            (what it is, install, run; links)
│                     every flag, notes) ├── AGENTS.md            (purpose, commands, conventions, map)
├── CLAUDE.md        (300 lines)         ├── CLAUDE.md            (@AGENTS.md)
├── docs/                                ├── docs/
│   ├── notes.md     (decisions + TODOs) │   ├── README.md        (index)
│   └── api.md       (outdated)          │   ├── how-to/          (only if there are tasks to describe)
└── .serena/memories/                    │   ├── reference/api.md (verified against the code)
    ├── overview.md  (copies README)     │   ├── explanation/     (only if there is a "why" to tell)
    └── commands.md  (contradicts it)    │   └── adr/0001-….md, 0002-….md (decisions from notes.md)
                                         └── .serena/memories/    (summary + link each; gotchas)
```

No tutorials folder appears, because this repo had no tutorial content. The audit does not invent pages.

### A worked example

The kit's eval for docs-audit builds a small CLI repo, `tasklog`, with eight planted errors and one genuinely ambiguous item. The [full before/after example](examples/docs-audit-before-after/README.md) (a **simulated example based on the kit's eval fixture**) shows every file, the claim table and the question asked. Three excerpts:

**AGENTS.md commands: plausible versus verified.**

```text
Before                                   After
| Test | `uv run pytest test/` |         | Test | `uv run pytest` |
| Lint | `make lint` |                   There is no linter configured.
```

The tests live in `tests/` and there is no Makefile. Every agent session loaded these two wrong lines.

**A memory that copied a table versus summary plus link.**

```text
Before (.serena/memories/project_overview.md)
| `tasklog add <title>` | Add a task. Titles may be up to 200 characters. |
... (the whole CLI table, copied from docs/reference/cli.md, which says 120)

After
tasklog: CLI task logger on SQLite. Commands and limits: `docs/reference/cli.md`; ...
```

The copy had already drifted: the code says `MAX_TITLE_LEN = 120`.

**A buried, undecided behaviour versus an ADR.** The docs said `list --all` "also shows archived tasks"; the code parsed the flag, ignored it, and had a TODO saying the intent was undecided. The audit asked instead of guessing, and the answer became `docs/adr/0001-archive-is-a-soft-delete.md`, with the reference now saying "accepted but not implemented yet".

## Adopting it

**With the kit**

| Situation | Steps |
|---|---|
| New project | `loadout init`, then `/loadout:onboard` in Claude Code |
| Existing repo | `loadout init` (never overwrites; if only a CLAUDE.md exists, it leaves it for onboard to migrate), then `/loadout:onboard` |
| Existing repo with messy docs | Then `/loadout:docs-audit` |
| Every feature | `/loadout:docs-sync` before merging |

`loadout init` scaffolds whatever is missing of AGENTS.md, CLAUDE.md (`@AGENTS.md`), `docs/README.md` and `docs/adr/README.md`, and adds `.claude/settings.local.json` and `.serena/cache/` to `.gitignore`.

**Without the kit**

1. Create `docs/README.md` as an index and `docs/adr/` with a one-line README describing the format.
2. Move your CLAUDE.md content into AGENTS.md, cut it to purpose, commands, hard conventions and a map, and make CLAUDE.md the single line `@AGENTS.md`.
3. Move every other fact into `docs/`, sorted by Diátaxis type, only creating the types you need. Delete the copies.
4. Turn decisions buried in notes, issues and commit messages into ADRs.
5. Shrink agent memories to one summary line and a link per topic.
6. Add "docs updated?" to your pull request checklist, and check links in CI.

## FAQ

**Isn't this overhead for a small project?**
For a small project it is a README, a 30-line AGENTS.md, a one-line CLAUDE.md and maybe two pages in `docs/`. That is less text than the usual README-plus-long-CLAUDE.md, not more. The overhead is in keeping copies in sync, and this model removes the copies.

**Where do I put X?**

| X | Home |
|---|---|
| How to install and run | README (short), details in `docs/how-to/` |
| Build/test/lint commands | AGENTS.md (agents need them on every task) |
| A config option, env var or default | `docs/reference/` |
| Why the system is shaped this way | `docs/explanation/` |
| A decision and its trade-offs | `docs/adr/NNNN-….md` |
| "This test is flaky unless X" | Serena memory (gotcha) |
| "To add an endpoint, touch these 3 files" | Serena memory (task recipe), or `docs/how-to/` if a human needs it too |
| Your personal coding preferences | Your personal layer, not the repo |
| A note that only matters on this machine | Claude Code auto memory |

**What about API docs generated from code?**
Then the code (docstrings, OpenAPI schema, type signatures) is the home, and the generator output is the reference. `docs/` links to it or hosts the generated pages; nobody hand-copies signatures. The audit only looks at doc comments where other docs refer to them.

**Do agents really follow this?**
The research says agents follow the instructions in context files well [Gloaguen 2026], and Claude Code's docs say specific, concise instructions are followed more consistently [Claude Code memory docs]. That is why the kit puts the policy into a few short rule files loaded in every session instead of a long manual. Following is not the same as remembering, though: that is what docs-sync at the end of a feature is for, and docs-audit when things have drifted anyway.

## Sources

Peer-reviewed:

- [Liu 2024] Liu, Lin, Hewitt, Paranjape, Bevilacqua, Petroni, Liang. *Lost in the Middle: How Language Models Use Long Contexts.* TACL 12, 2024. <https://doi.org/10.1162/tacl_a_00638>
- [Aghajani 2019] Aghajani et al. *Software Documentation Issues Unveiled.* ICSE 2019. <https://doi.org/10.1109/ICSE.2019.00122>
- [Aghajani 2020] Aghajani et al. *Software Documentation: The Practitioners' Perspective.* ICSE 2020. <https://doi.org/10.1145/3377811.3380405>
- [Jansen & Bosch 2005] Jansen, Bosch. *Software Architecture as a Set of Architectural Design Decisions.* WICSA 2005. <https://doi.org/10.1109/WICSA.2005.61>

Preprints and reports:

- [Gloaguen 2026] Gloaguen, Mündler-Sasahara, Müller, Raychev, Vechev. *Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?* arXiv:2602.11988. <https://arxiv.org/abs/2602.11988>
- [Lulla 2026] Lulla, Mohsenimofidi, Galster, Zhang, Baltes, Treude. *On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents.* arXiv:2601.20404. <https://arxiv.org/abs/2601.20404>
- [Shahbazian 2017] Shahbazian, Lee, Le, Medvidovic. *Uncovering Architectural Design Decisions.* arXiv:1704.04798. <https://arxiv.org/abs/1704.04798>
- [Hong 2025] Hong, Troynikov, Huber. *Context Rot: How Increasing Input Tokens Impacts LLM Performance.* Chroma technical report, 2025. <https://research.trychroma.com/context-rot>

Practitioner sources:

- [Diátaxis] Daniele Procida. *Diátaxis.* <https://diataxis.fr/> (axes: <https://diataxis.fr/foundations/>)
- [Canonical 2021] Daniele Procida. *Diátaxis, a new foundation for Canonical documentation.* <https://canonical.com/blog/diataxis-a-new-foundation-for-canonical-documentation>
- [Nygard 2011] Michael Nygard. *Documenting Architecture Decisions.* <https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions>
- [adr.github.io] *Architectural Decision Records.* <https://adr.github.io/>
- [Thoughtworks 2018] Thoughtworks Technology Radar. *Lightweight Architecture Decision Records* (Adopt, May 2018). <https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records>
- [Write the Docs] *Docs as Code.* <https://www.writethedocs.org/guide/docs-as-code/>
- [agents.md] *AGENTS.md.* <https://agents.md/>
- [Anthropic 2025] Anthropic. *Effective context engineering for AI agents.* <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- [Claude Code memory docs] Anthropic. *How Claude remembers your project.* <https://code.claude.com/docs/en/memory>
