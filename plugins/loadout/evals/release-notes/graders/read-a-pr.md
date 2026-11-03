---
type: regex
target: { source: file, path: .gh-calls.log }
pattern: "(?:^|\\n)pr view (?:41|42|43) --json title,body"
---
