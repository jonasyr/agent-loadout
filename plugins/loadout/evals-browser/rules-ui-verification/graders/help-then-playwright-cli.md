---
type: regex
target: { source: file, path: .browser-calls.log }
# first browser call is `playwright-cli --help`, later a real playwright-cli command
pattern: "^playwright-cli (?:--help|-h|help)\\s*\\n(?:.*\\n)*?playwright-cli (?:open|goto|screenshot|snapshot|resize)\\b"
weight: 3
---
