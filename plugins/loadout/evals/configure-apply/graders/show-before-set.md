---
type: tool_order
before: { tool: Bash, input_match: "loadout\\s+configure\\s+show" }
after: { tool: Bash, input_match: "loadout\\s+configure\\s+set" }
weight: 2
---
