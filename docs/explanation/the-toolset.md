# The toolset

loadout does not install a pile of tools. It installs a small set where each one does one job, and rules that tell your agent (Claude Code or Codex) which tool to use for which question. Together they form one workflow, from a rough idea to a reviewed, documented change. This page explains that workflow and why each tool is in it. The exact list, with settings and versions, is in [Included tools](../reference/included-tools.md).

## One change, start to finish

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/toolset-workflow.dark.svg">
  <img alt="An idea or a bug goes through three stages. Think first: brainstorming, writing-plans, then execution-advisor. Build: a test-driven build, with codebase-memory, Serena and LSP diagnostics for the code, Context7 and Microsoft Learn for libraries, and frontend-design, playwright-cli and impeccable for UI work. Finish: review, /loadout:docs-sync, then commit-commands. rtk shrinks command output in every step." src="../diagrams/toolset-workflow.light.svg">
</picture>

<sub>[Source](../diagrams/toolset-workflow.mmd)</sub>

Blue boxes are loadout's own skills. Orange boxes are skills from plugins the kit enables (and the agent's built-in review). Amber boxes are groups of tools your agent reaches for while it works: MCP servers, plugins and command-line tools. Grey dashed boxes are the starting point and rtk, which a hook applies on its own. The tinted frames only tell the three stages apart.

The kit's rules make this the default path, not a suggestion you have to remember: `workflow.md` sends Claude through the process skills, and `tooling.md` routes each question to the right tool. Both are loaded in every session ([The loadout plugin](../reference/included-tools.md#the-loadout-plugin)).

The full workflow runs in Claude Code (CLI or the Claude Code extension), in the Codex CLI and in VS Code's Codex extension. In the extension, approve the hooks once (the hooks icon in the prompt bar, then Allow all) before the hooks below run ([Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)).

## Think first

- **[superpowers](https://github.com/obra/superpowers)** (plugin) brings the process skills. *brainstorming* asks what you want before anything is built and writes the agreed design down as a spec. *writing-plans* turns the spec into small tasks, each with its test first and the exact files to touch. *systematic-debugging* finds the cause of a bug before it gets patched, and *verification-before-completion* stops "done" being claimed without evidence.
- **`/loadout:execution-advisor`** (loadout skill) reads a finished plan and recommends how to run it: in the current session, with a fresh subagent per task, or a mix, with a model per task and a review policy. It replaces superpowers' default of always using subagents, which costs more than most plans need ([ADR 0014](../adr/0014-execution-advisor-instead-of-default-sdd.md), [The execution advisor](execution-advisor.md)).

## Build

- **Test-driven build.** superpowers' *test-driven-development* and *executing-plans* skills: write the failing test, watch it fail, make it pass, commit.
- **Know the code.** Two MCP servers answer different questions ([ADR 0008](../adr/0008-code-intelligence-routed-by-rule.md)):
  - **[codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)** indexes the repo into a knowledge graph. It answers structure questions (who calls this, what does a change affect, what is dead code) in one query instead of many file reads.
  - **[Serena](https://github.com/oraios/serena)** works on exact symbols: find a definition and its references, rename, replace a function body. Commit its `.serena/project.yml` and `.serena/memories/`, so a teammate gets the same project setup and notes. Serena writes `.serena/.gitignore` itself, with `/cache` and `/project.local.yml` (your local overrides); leave those out of git, and add nothing else for them.
  - The **LSP plugins** ([pyright](https://github.com/microsoft/pyright), [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server), [rust-analyzer](https://github.com/rust-lang/rust-analyzer), through [Anthropic's official plugins](https://github.com/anthropics/claude-plugins-official)) report type errors right after each edit, so Claude fixes them before it moves on. They exist for Claude Code only; in the Codex CLI the loadout plugin's type-check hook runs the language's checker on the changed files instead ([ADR 0024](../adr/0024-codex-parity-update-model.md)).
- **Know the libraries.** **[Context7](https://github.com/upstash/context7)** fetches current documentation for a library or framework, and **[Microsoft Learn](https://github.com/MicrosoftDocs/mcp)** does the same for .NET, Azure and Windows. Claude uses them before web search and instead of its training data, which may be out of date.
- **UI work.** **[frontend-design](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/frontend-design)** sets a distinctive direction, **[playwright-cli](https://github.com/microsoft/playwright-cli)** checks the result in a real browser at phone, tablet and desktop widths, and **[impeccable](https://github.com/pbakaus/impeccable)** audits and polishes it ([ADR 0009](../adr/0009-design-tooling-frontend-design-and-impeccable.md)). playwright-cli keeps screenshots and page snapshots on disk instead of in Claude's context, which is why it is the default over a browser MCP server ([ADR 0013](../adr/0013-playwright-cli-instead-of-browser-mcp.md)).
- **[rtk](https://github.com/rtk-ai/rtk)** (command-line tool) rewrites shell commands through a proxy that strips noise from their output, so test runs and git logs cost fewer tokens. A plugin hook applies it automatically (in Codex, once the hooks are approved).

## Finish

- **Review.** One review pass per change: Claude Code's built-in `/code-review` (in Codex, the built-in `/review`), or superpowers' *requesting-code-review*. **[security-guidance](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/security-guidance)** warns about security mistakes while code is written and reviews each commit.
- **Documentation.** **`/loadout:docs-sync`** updates the docs a change made wrong, and **`/loadout:docs-audit`** checks a whole repo's docs against its code. Where each fact belongs is in [Documentation strategy](documentation-strategy.md).
- **Commit.** **[commit-commands](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/commit-commands)** commits, pushes and opens pull requests. **[claude-md-management](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/claude-md-management)** keeps `CLAUDE.md` files healthy.

## Per project, not everywhere

Domain tools add skill descriptions and tools to every session they are enabled in, so the kit enables them only in the repos that need them, with `loadout profile NAME` ([ADR 0007](../adr/0007-tiered-scoping-with-profiles.md)). For example, the `thesis` profile adds [academic-research-skills](https://github.com/Imbad0202/academic-research-skills), [deepeval](https://github.com/confident-ai/deepeval) and [huggingface-skills](https://github.com/huggingface/skills), and the `db` profile adds [DBHub](https://github.com/bytebase/dbhub). All profiles: [Per-project profiles](../reference/included-tools.md#per-project-profiles).

## Left out on purpose

Some popular tools are not in the kit because they overlap with what is there or cost context in every session. Each one has a `superseded`, `deprecated` or `alternative` entry with its reason in [`catalog.json`](../../catalog.json), and `loadout adopt` explains it when it finds one on your machine. Examples: memory plugins that rewrite `CLAUDE.md` after most turns (native auto memory and the docs model cover it), a browser MCP server as the default (playwright-cli is cheaper), and skill collections with hundreds of entries (copy the few you need into a project). The optional add-ons you can turn on yourself are in [Included tools](../reference/included-tools.md#optional-global-add-ons).
