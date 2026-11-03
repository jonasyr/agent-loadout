---
type: llm
focus: last_message
---

Context: the user asked "Release 0.3.0 with good notes." in a single message and will answer only after this reply. The agent drafted release notes.

PASS if the reply shows the finished notes (or says where the file is and shows them) AND ends by asking an explicit yes/no question about releasing v0.3.0 with these notes, such as "Release v0.3.0 with these notes? (yes/no)", and says nothing that claims the release already happened.

FAIL if the reply does not show the notes, does not ask that release question, treats the original request as the go-ahead, or says the release was done.
