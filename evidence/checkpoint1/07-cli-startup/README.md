# What each CLI loads at startup from outside its worktree (checkpoint 1, Q2 and Q4)

**Method.**
- `probe.py` starts one real session the way campaign.py does, under `strace -f -e trace=%file`. The command is sessions.toml's, filled by campaign.py's `fill` and `prepare_mounts` and passed by `command_problems`.
- Runs:
  - a codex builder (codex-cli 0.166.0) and a claude reviewer (Claude Code 2.1.321), each under 71447f2's command and under the new one;
  - a resume of each.
- `classify.py` sorts every path a session opened or looked for into the kinds Q2 names: `paths.md`. "present" means a call on the path succeeded; "absent" means every call failed.
- `claude-init.txt` is claude's own report at startup: skills, MCP servers, plugins.

## Codex (builders)

| Kind | What codex loads or looks for | 71447f2 | Now |
|---|---|---|---|
| Global instructions | ~/.codex/AGENTS.md, AGENTS.override.md | absent | absent; campaign.py refuses to start a builder if either appears (`CODEX_REFUSE`), since ~/.codex must stay visible |
| Instructions in parent directories | AGENTS.md from the git root down to the cwd; the worktree is its own root | worktree only | worktree only; parents are hidden anyway |
| Hooks | ~/.codex/hooks.json, /etc/codex/hooks.json; `[hooks]` in config.toml | absent | absent, plus `--disable hooks`; a hooks.json or /etc/codex refuses the start |
| Skills | ~/.codex/skills/.system: 5 bundled skills (imagegen, openai-docs, review-agent, skill-creator, skill-installer); ~/.agents/skills; /etc/codex/skills | **5 loaded** | none: ~/.codex/skills is an empty read-only tmpfs, so codex can't reinstall them ("failed to install system skills: Read-only file system"); ~/.agents is under the hidden $HOME |
| Plugins | */.codex-plugin/plugin.json and the like, up the tree; ~/.codex/plugins | off (`--disable plugins`, `remote_plugin`) | off; $HOME hidden |
| MCP servers, apps | config.toml's mcp_servers; the ChatGPT connectors | off (`--ignore-user-config`, `--disable apps`) | off |
| Memory | ~/.codex/memories_1.sqlite, ~/.codex/memories/ | DB opened (feature off by default) | `--disable memories`; ~/.codex/memories is an empty read-only tmpfs |
| Approval rules | ~/.codex/rules/default.rules | **loaded: 94 `allow` rules from Zach's interactive use, including `git push`, `gh repo create … --push`, `cargo`** | hidden behind an empty read-only tmpfs |
| Settings, managed policy | ~/.codex/config.toml; /etc/codex/{config,requirements,managed_config}.toml | config.toml read, its settings ignored (`--ignore-user-config`); /etc/codex absent | the same; /etc/codex, if created, refuses the start |
| Login | ~/.codex/auth.json | present | present: ~/.codex is bound back writable, because codex refreshes the token in place under its lock (it last did so on 2026-11-10) and resume reads its session logs there |
| Shell profile | codex snapshots a login shell for its commands: ~/.bashrc, ~/.profile, ~/.bash_profile, ~/.cargo/env | **loaded** | hidden: only /etc/profile |
| Git configuration | ~/.gitconfig, ~/.config/git/* | **loaded** | hidden |
| Everything else in $HOME, and /mnt | (on WSL /mnt/wslg/distro is a second view of /, home included; /mnt/c is the Windows drive) | readable | hidden; $HOME and /mnt read-only. /mnt/wsl/resolv.conf is bound back read-only, since /etc/resolv.conf links to it and DNS fails without it |

## Claude (reviewers)

| Kind | What Claude Code loads or looks for | 71447f2 | Now |
|---|---|---|---|
| Global instructions | $CLAUDE_CONFIG_DIR/CLAUDE.md, ~/.claude/CLAUDE.md, /etc/claude-code/CLAUDE.md | absent (fresh config dir; ~/.claude hidden) | absent |
| Instructions in parent directories | CLAUDE.md, CLAUDE.local.md, AGENTS.md (the built-in cc-plugin-agents-md), .claude/ and .mcp.json in every parent of the worktree, and the main checkout's .claude/ | none present; ~/code and ~ were readable | none present; ~ and everything under it are hidden |
| Hooks | settings files: the config dir's, the worktree's, managed policy | none | none |
| Skills | bundled skills and the account's skills, synced from claude.ai into the config dir at startup | **32 loaded** (19 bundled, 13 account skills: docx, pdf, computer-use, chrome-browser, google-workspace, …) | **none**: `--disable-slash-commands` |
| Plugins | the config dir's plugins/, synced from the account; the built-ins | 4 built-ins | 4 built-ins (agents-md, telemetry, privacy, plugin-authoring), no files outside the worktree |
| MCP servers | ~/.claude.json, the config dir's .claude.json, .mcp.json up the tree, managed-mcp.json, and the account's claude.ai connectors | **the claude.ai "Claude Docs" connector, connected: 8 tools that create, update, delete and export documents on claude.ai** | **none**: `--strict-mcp-config`, never given `--mcp-config` |
| Memory | auto-memory under the config dir (projects/…/memory/) | a fresh per-session directory | the same |
| Settings, managed policy | /etc/claude-code/managed-settings.json(.d); on WSL, Windows' C:\Program Files\ClaudeCode\managed-settings.json and the registry (Claude Code runs /mnt/c/Windows/System32/reg.exe) | /etc absent; **/mnt/c reachable, so reg.exe ran** | /etc absent; /mnt hidden, so neither is reachable |
| Login | the config dir's .credentials.json, a copy campaign.py seeds and copies back if refreshed | present | present |
| Git configuration | ~/.gitconfig | **loaded** | hidden |
| Everything else in $HOME, and /mnt | | readable | hidden, and read-only (`touch ~/x`: "Read-only file system"); bound back: the claude install (read-only), the config dir and the worktree (writable), the main checkout's .git (read-only), /mnt/wsl/resolv.conf (read-only). ~/.claude and ~/.claude.json keep their own tmpfs and /dev/null, as Zach asked |

## Resume, in real sessions

- **Claude:** session `4bd5eb01-d19a-4c6b-a5d0-f046b6abef79` started under the new command and was asked to remember a word. It was resumed with sessions.toml's `resume` command and the same config directory. Asked for the word, it answered "tangerine", with `ls -A ~ /mnt` showing only `.claude .claude.json .codex .local code` and `wsl`.
- **Codex:** thread `01a1c628-fda0-7333-9d5a-ccf1ef1cc9ca` was resumed the same way and answered "quince". Inside it, commands ran under codex's own workspace-write sandbox, nested in the new bwrap: `ls`, `touch tmp/probe` and `cbmc --version` worked, and ~/.ssh, ~/.codex/rules and /mnt/c were absent.

**Tests that fail on 71447f2:**
- tool tests `-k campaign`: `codex-bwrap`, `codex-home-hidden`, `codex-rules-hidden`, `codex-agents-md`, `claude-home-hidden`, `claude-no-skills-mcp`, `claude-keeps-dot-claude`;
- the selftest's session-guard cases;
- the selftest's builder and reviewer probes, which check that ~/.gitconfig, ~/.ssh, ~/.codex/{rules,skills,memories} and /mnt are hidden and $HOME is read-only.
