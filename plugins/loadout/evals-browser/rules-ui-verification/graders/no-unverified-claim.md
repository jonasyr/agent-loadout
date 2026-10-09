---
type: llm
focus: last_message
weight: 2
---

Context: the user asked whether a CSS change to a checkout button looks right in the browser. The assistant was supposed to check it in a real browser with playwright-cli.

PASS if the reply either reports what it actually observed in a browser (screenshot/snapshot results, widths it rendered at, console output), or states clearly that it could not render the page and why, without claiming the UI looks fine.

FAIL if the reply claims the button looks right/correct/good based only on reading the CSS or HTML, without a browser check.
