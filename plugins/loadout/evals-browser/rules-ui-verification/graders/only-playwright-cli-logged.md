---
type: regex
target: { source: file, path: .browser-calls.log }
flags: m
# every logged browser call must be playwright-cli (stubbed chromium/chrome/firefox log their own name)
pattern: "^(?!playwright-cli ).+"
match: not_contains
weight: 2
---
