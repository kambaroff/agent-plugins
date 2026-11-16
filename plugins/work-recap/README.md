# work-recap

A factual recap of your previous work day or week, built from records instead of memory: the forge's
activity feed, the repository's history and the notes written along the way.

## Installation

**Claude Code:**
```bash
/plugin marketplace add https://github.com/kambaroff/agent-plugins
/plugin install work-recap
```

**Codex CLI:**
```bash
codex plugin marketplace add kambaroff/agent-plugins
codex plugin add work-recap@agent-plugins
```

Version: 0.1.0

## What's New in 0.1.0

- First release: `/recap` for a day or a week, `scripts/recap.py` with tests.

## Why

"What did I do yesterday" is answered from memory, and memory drops the review of someone else's merge
request, the third re-approval after a push and the finding that was never posted. The forge already has
a record of every push, comment and approval; this command reads it, adds what only the repository and
your notes know, and groups all of it by ticket.

## Requirements

- `python3` (3.9 or newer) for the helper script;
- `glab` for GitLab or `gh` for GitHub, signed in — or a forge MCP server with the same read access;
- `git`.

## Usage

```bash
/recap                           # the previous work day; on Monday that is Friday
/recap week                      # the last completed week, Monday to Sunday
/recap this-week                 # Monday through today
/recap 2026-11-13                # one day; also 13.11 or friday
/recap 2026-11-09..2026-11-13    # a range
/recap week --standup            # plus a short text for the team
```

1. Works out the period in your time zone: a day is a local day, so an event late in the evening is not
   lost to the UTC date.
2. Reads the forge's activity feed for the account — every project, not only the current repository —
   and digests it: pushes, comments with `path:line`, approvals, requests opened, merged and closed.
3. For the merge requests you commented on or approved, reads what stood behind it: whose request it is,
   which thread a comment opened or answered, what the author replied, why an approval repeats.
4. Adds your commits from the local history, and the ones that were never pushed.
5. Reads the notes dated inside the period (`notes`) and follows `extra` for sources of your own.
6. Reports by ticket: own work, reviews, analysis and notes, other — and, on its last line, the sources
   it could not reach. A week adds the state of each item at the end of the range and an index by day.

Nothing is written anywhere: no comments, approvals, pushes or files in the repository.

## Configuration

`~/.claude/work-recap.md` (user) and `.claude/work-recap.local.md` (project, wins key by key). Keys and
defaults: [`config-defaults.md`](config-defaults.md) — `forge`, `timezone`, `workdays`, `repos`,
`notes`, `extra`, `language`, `standup_language`.

## Script

`scripts/recap.py` has two subcommands, both covered by `tests/test_scripts.py`:

- `recap.py window [<period>] [--tz <zone>] [--workdays <1,2,..>] [--today <date>] [--json]` — the
  period in local dates, its bounds in UTC and the dates to ask the feed for. `<zone>` is an IANA name,
  an offset (`+05:00`) or `local`.
- `recap.py feed --forge <gitlab|github> --start <utc> --end <utc> [--tz <zone>] [--body <n>] [--json] <events.json>…`
  — the events inside the window, grouped by project and merge request, with the totals. Reads the
  GitLab `events` and GitHub `users/<login>/events` formats; several pages in one file are fine.

Exit code 0; 1 when the feed holds nothing inside the window; 2 on bad input.

## Codex

The command becomes a Codex skill through `plugin-cross-port`; the script is bundled into it. Nothing
here relies on subagents.
