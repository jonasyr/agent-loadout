---
name: release
description: Cut a loadout release with good notes - draft the Keep a Changelog section from the merged PRs, rewrite it for people who use loadout, and release only after the person says yes to it. Use when the user asks to release, cut a release, publish vX.Y.Z or write release notes.
---

# Release

Drive `loadout release` in two steps: a draft first, a release only after an explicit yes. Its reference is `docs/reference/cli.md`, section "loadout release", in the folder `loadout kit-path` prints. In Codex this skill is `$loadout:release`.

Never edit `CHANGELOG.md` yourself and never run a git or gh command that writes: `loadout release` does all the writing. `gh` is for reading PRs only.

1. **Version.** If the person gave none, ask. Suggest the next one from the last tag (`git tag --list 'v*' --sort=-v:refname`) and the draft's sections: a patch for fixes only, a minor when there is an Added or Changed entry. Never suggest a major version; the person decides that.
2. **Draft.** Run `loadout release X.Y.Z --draft-notes <tmp file>` (a path in your scratch or temp folder). It runs every check the release runs and writes only the draft. If it refuses, show the refusal as printed and stop.
3. **Read the PRs.** For each `(#N)` in the draft run `gh pr view N --json title,body`. Read-only; skip a PR whose lookup fails and keep its line as it is.
4. **Rewrite the draft:**
   - Fill the summary comment with 1-3 sentences for people who use loadout, and remove the comment.
   - One plain line per user-visible change, in words a user understands, not commit wording.
   - Merge related PRs into one line and keep every `(#N)` on it.
   - Drop lines that only matter inside the repo (refactors, tests, CI, docs-only), unless a user would notice.
   - Keep the section order (Breaking, Added, Changed, Fixed, Security), the heading `## [X.Y.Z] - YYYY-MM-DD` and the compare link line exactly as drafted.
   - Invent nothing: every claim comes from a PR title or body.
5. **Show it.** Write the result back to the draft file, show the whole file, and ask exactly: "Release vX.Y.Z with these notes? (yes/no)". Wait for the answer.
6. **Release only on an explicit yes to that question.** "Looks good", "nice" or the original request are not a yes. Then run `loadout release X.Y.Z --notes <file> --yes` and report its output as printed. On anything else, or on no answer, stop and say the file's path and the command to run later: `loadout release X.Y.Z --notes <file> --yes`. If the person wants changes, edit the file and ask the question again.
