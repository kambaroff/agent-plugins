# agent-plugins

Claude Code and Codex plugins. Each plugin is written for Claude Code; the Codex skills next to it are
generated with [`plugin-cross-port`](https://github.com/IvanLutsenko/awac-ai-agent-plugins/tree/main/plugins/plugin-cross-port).

## Plugins

- [`android-verify`](plugins/android-verify) — `/emu-verify` checks an Android change on an emulator or
  a device over plain `adb` (build identity, a person signs in, scenario driven from uiautomator dumps,
  screenshots and backend responses in the report); `/gradle-run` runs Gradle with its output in a log
  and reads a summary instead of thousands of lines.
- [`plan-gate`](plugins/plan-gate) — `/plan-gate`: the plan is written and shown first, nothing changes
  until a person approves it, an executor agent on a cheaper model carries it out, and the diff is
  checked against the plan before the report.

## Installation

**Claude Code:**
```bash
/plugin marketplace add https://github.com/kambaroff/agent-plugins
/plugin install android-verify
/plugin install plan-gate
```

**Codex CLI:**
```bash
codex plugin marketplace add kambaroff/agent-plugins
codex plugin add android-verify@agent-plugins
codex plugin add plan-gate@agent-plugins
```

## Layout

```
.claude-plugin/marketplace.json        Claude Code marketplace
.agents/plugins/marketplace.json       Codex marketplace
plugins/<name>/.claude-plugin/         plugin manifest (source of truth)
plugins/<name>/.codex-plugin/          generated Codex manifest
plugins/<name>/skills/generated-from-* generated Codex skills
plugins/<name>/tests/                  tests of the plugin's scripts
```

## Changing a plugin

1. Edit the Claude Code side: `commands/`, `agents/`, `scripts/`, `README.md`.
2. Bump `version` in `plugins/<name>/.claude-plugin/plugin.json`, in the plugin's README and in
   `.claude-plugin/marketplace.json`.
3. Regenerate the Codex side: `python3 <plugin-cross-port>/scripts/cross_port.py --repo-root . marketplace sync`.
4. `python3 -m unittest discover -s plugins/<name>/tests` when the plugin has tests.

CI runs the tests on Linux and Windows and checks that the Codex side is in sync.

## Mirroring into another marketplace

`.githooks/pre-push` can copy plugins whose version was bumped into a second marketplace (for example,
a private one) with a mirror script you keep outside this repository. It does nothing until configured
and never blocks a push.

```bash
git config core.hooksPath .githooks
mkdir -p ~/.config/agent-plugins
cat > ~/.config/agent-plugins/mirror.conf <<'CONF'
MIRROR_SCRIPT="$HOME/.claude/scripts/mirror-plugin.sh"
MIRROR_DST="$HOME/projects/other-marketplace"
MIRROR_TICKET_android_verify=ABC-1
MIRROR_TICKET_plan_gate=ABC-2
CONF
```

On a push to `main` the hook exports the pushed commit (not the working tree), finds plugins whose
`plugin.json` changed, and runs
`MIRROR_SRC=<export> MIRROR_DST=… MIRROR_TICKET=… "$MIRROR_SCRIPT" <plugin>` for each of them
(`--category` is added when `MIRROR_CATEGORY_<plugin>` is set). Plugin names map to variables with
`-` replaced by `_`. The mirror script is expected to commit in `MIRROR_DST` and leave the push to you.
Where `rsync` is missing (Git for Windows), `.githooks/bin/rsync` stands in for the
`rsync -a --delete --exclude … SRC/ DST/` form.

## License

MIT
