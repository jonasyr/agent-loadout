# The real Claude Code at the end of the README demo: a fresh project after `loadout init`, then /loadout:onboard.
# Recorded by the maintainer with demo/record-claude.sh (it uses their Claude Code login and a little plan usage).
# No Wait commands: VHS reads Wait from the top of the scrollback, so it cannot follow a full-screen app.
Output demo/claude-clip.mp4
Require claude
Require loadout
Source demo/style.tape

Hide
Type `cd "$(mktemp -d)" && mkdir my-app && cd my-app && printf '{"name":"my-app","private":true,"dependencies":{"react":"^19.0.0"},"devDependencies":{"typescript":"^5.6.0","vite":"^6.0.0"}}\n' > package.json && mkdir src && printf 'export function App() {\n  return <h1>Hello</h1>;\n}\n' > src/App.tsx && loadout init --yes --no-install >/dev/null && git add -A >/dev/null && git commit -qm init && PS1='\[\e[35m\]~/my-app ❯\[\e[0m\] ' && clear`
Enter
Sleep 4s
Show
Sleep 500ms
Type "claude"
Sleep 500ms
Enter
# the folder is new, so Claude Code asks whether to trust it; Enter accepts
Sleep 5s
Enter
Sleep 4s
Type "/loadout:onboard"
Sleep 800ms
Enter
Sleep 14s
