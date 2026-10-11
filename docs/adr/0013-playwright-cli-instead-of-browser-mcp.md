# 0013. playwright-cli instead of a browser MCP server

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, section 4.1](../superpowers/specs/2026-10-08-agent-loadout-design.md#41-global-settingsbasejson) (core binary Playwright CLI) and the catalog entries `playwright-cli`, `mcp-playwright`, `mcp-puppeteer`

## Context
UI work must be checked in a browser. A browser MCP server adds its tool descriptions to every session and returns snapshots and screenshots into the context. The Playwright CLI is a plain command that writes those to disk.

## Decision
`@playwright/cli` is a core binary (`required: true` in the catalog). The agent learns it from `playwright-cli --help` and the routing rule, with no skill and no MCP server, so it adds no idle context. The Playwright MCP plugin stays in the catalog as an alternative. The `web` profile adds richer guidance (`playwright-cli install --skills`) for repos that need it.

## Alternatives considered
- The Playwright MCP plugin: roughly four times more tokens for the same work, because snapshots and screenshots enter the context.
- Puppeteer MCP server: archived, marked superseded in the catalog.
- chrome-devtools-mcp: kept in the `web` profile, off by default, for performance and network debugging.

## Consequences
- Lower token use for browser checks. Screenshots and snapshots stay on disk and the agent opens only what it needs.
- It is one more binary to install and update ([0011](0011-tool-binaries-notice-and-deliberate-update.md)).
- The rule "verify UI in a browser" depends on the binary being present. `loadout check` reports it when missing.

## In the code
- `catalog.json` (`playwright-cli`: status core, required; `mcp-playwright`: status alternative; `mcp-puppeteer`: status superseded)
- `rules/tooling.md` and `rules/workflow.md` (UI verification)
- `profiles/web.json` (`commands`)
