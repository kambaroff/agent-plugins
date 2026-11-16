---
name: work-recap-recap
description: List everything you did on the previous work day, a given date or a whole week: commits, merge requests opened and merged, review threads, replies, approvals and the notes written along the way, grouped by ticket. Use when the user invokes /recap.
version: 0.1.0
---

> Converted from Claude Code command `/recap`.
> Review and adapt: hooks and MCP tool IDs may need manual mapping for Codex.
> Helper scripts ship in this skill's own `scripts/` directory. Replace
> `<this skill directory>` with the path Codex reported when it loaded this skill —
> a bare relative path would resolve against the repository under review instead.

# Recap

A factual list of what one person did over a work day or a week, built from records, not from memory:
the forge's activity feed, the repository's history and the notes written during the work.

**Read-only.** Nothing is posted, approved, resolved, pushed, transitioned or written into the
repository. Every `glab api` / `gh api` call here is a GET.

## Arguments

**$ARGUMENTS**

- nothing or `day` — the previous work day; weekends are stepped over;
- `week` — the last completed week, Monday to Sunday; `this-week` — Monday through today;
- a date (`2026-11-13`, `13.11`), a weekday (`friday`), or a range (`2026-11-09..2026-11-13`);
- `--standup` — after the recap, add a short text for the team (Step 8).

## Step 0 — Config

```bash
cat .claude/work-recap.local.md 2>/dev/null    # project-level, wins
cat ~/.claude/work-recap.md 2>/dev/null        # user-level
```

Keys and defaults: `plugins/work-recap/config-defaults.md` — `forge`, `timezone`, `workdays`,
`repos`, `notes`, `extra`, `language`, `standup_language`.

## Step 1 — The period

```bash
python3 "<this skill directory>/scripts/recap.py" window <period> --tz "<timezone>" --workdays "<workdays>" --json
```

It prints the local dates (`first`, `last`), the bounds in UTC (`start_utc`, `end_utc`), the dates for the
activity feed (`feed_after`, `feed_before`) and `mode` — `day` or `week`. A day is a local day: an event
at 23:30 UTC may belong to the next one. Never filter by the UTC date yourself; pass the bounds on.

Exit 2 with `unknown time zone` (no IANA data, usual on Windows): pass the offset, `--tz +05:00`.

## Step 2 — The activity feed

Forge: `forge` from the config, otherwise by the `origin` remote — `github.com` → GitHub, anything else →
GitLab. The feed covers every project the account touched, not only this repository.

GitLab:
```bash
glab api --paginate "events?after=<feed_after>&before=<feed_before>&per_page=100" > "<tmp>/events.json"
python3 "<this skill directory>/scripts/recap.py" feed --forge gitlab --start <start_utc> --end <end_utc> --tz "<timezone>" "<tmp>/events.json"
```

GitHub:
```bash
gh api user --jq .login
gh api --paginate "users/<login>/events?per_page=100" > "<tmp>/events.json"
python3 "<this skill directory>/scripts/recap.py" feed --forge github --start <start_utc> --end <end_utc> --tz "<timezone>" "<tmp>/events.json"
```

`<tmp>` is a directory outside the repository (`mktemp -d`). The script keeps the events inside the
window and prints them by project and merge request: pushes (merge pushes folded into one line),
comments with `path:line` and the first line of the text, approvals, opened / merged / closed, and the
totals. `--json` gives the same as data; `--body <n>` changes how much of a comment is kept.

- Exit 1 — nothing inside the window. In day mode with no period given, the day may have been a day off:
  run Step 1 again with `--today <that day>` to get the work day before it, at most five times, and say
  in the report's first line which day was used and why.
- GitLab names projects by id; `glab api "projects/<id>" --jq .path_with_namespace` turns one into a name.
- GitHub keeps about 90 days and 300 events; an older period is reported from Steps 4–5 only, and the
  report says so.

**No `glab` / `gh`, but a forge MCP server is connected.** Use its tools for the same GETs. With an
events tool, save its output and run the script on it. Without one, rebuild the feed from three lists:
merge requests authored by you and merge requests where you are a reviewer, both updated since
`start_utc` (no upper bound — a later update must not hide a request touched inside the window), and
commits by you between `start_utc` and `end_utc`; then, per request, the notes written inside the window.
Your own notes are the activity: comments, and the system notes "approved", "resolved all threads",
"added N commits".

## Step 3 — What stood behind each merge request

Only for requests where you commented, approved, opened or merged — not for every push.

- GitLab: `glab api "projects/<id>/merge_requests/<iid>"` and
  `glab api "projects/<id>/merge_requests/<iid>/notes?sort=desc&per_page=100"`.
- GitHub: `gh api "repos/<owner>/<repo>/pulls/<n>"`, `…/pulls/<n>/reviews`, `…/pulls/<n>/comments`.

Take from them: title, author, source → target, state now; whose request it is (yours → own work,
someone else's → review); for each comment of yours, whether it opened a thread or answered one, and
the thread's point in a phrase; the other side's answer inside the window; and why an approval
repeats — a push that reset approvals in between makes the next one a re-approval. A push after your
last approval that reset it again is worth one clause.

In week mode fetch this only where the feed alone does not show how the request ended.

## Step 4 — Commits

In this repository and in each path from `repos`:

```bash
git log --all --no-merges --author="$(git config user.email)" --since="<first> 00:00" --until="<last> 23:59" --date=format:"%m-%d %H:%M" --pretty=format:"%h %ad %s"
git log --branches --not --remotes --no-merges --author="$(git config user.email)" --since="<first> 00:00" --until="<last> 23:59" --pretty=format:"%h %D %s"
```

The first is what was committed; the second is what never left the machine — report those as
"local, not pushed", with the hash. Merge commits (the target branch merged in, a chain of stacked
branches forwarded) are one line per pass, never a work item of their own.

## Step 5 — Notes and other sources

- `notes` — a glob of files written during the work (handoffs, review reports, analysis). Take the ones
  whose name carries a date inside the period (`2026-11-13`) and read them. They hold what a forge
  cannot: findings that were deliberately not posted, verdicts, decisions, checks on a stand or a device,
  work in systems without an API. Take the outcome, not the process; where a later note supersedes an
  earlier one, the state comes from the later, the per-day actions from the earlier.
- `extra` — free-form instructions for sources this command does not know: a tracker reachable through
  an MCP tool, a second forge, a team's worklog. Follow them read-only. If a source it names cannot be
  reached, do not go around it — name it in the report's last line.

## Step 6 — Merge

- Group by ticket or merge request, not by source: a commit, the push that carried it, the note about
  it and the tracker transition for the same ticket are one item.
- Split by the request's author: your own work, and review of other people's work.
- Every statement traces to a record inside the period. A note about an earlier day is context.
- A source that was reached and returned nothing is said plainly; a source that could not be reached
  goes to the last line. Never fill a gap from memory.

## Step 7 — Report

In the conversation, in `language` (default: the language the person writes in). Titles, ticket text and
UI strings stay as written. First line: the period and the totals.

**Day**

```
Recap for Fri 13.11.2026: 1 own ticket (3 requests touched), 3 commits, 10 review replies; 6 requests reviewed, 3 threads posted, 9 approvals

Own work
- ABC-101, !77 "<title>" (-> target)
  - commits: <title>; <title>
  - replied in 10 review threads: fixed path/to/File.kt:42, <point>; answered without a change …
  - forwarded through the stacked branches twice

Reviews
- !96 ABC-140, <author>: first review, 2 threads
  - path/to/File.kt:78: <point of the thread>; author fixed it
  - approved 17:12; a push at 20:45 reset it
- !44 ABC-96, <author>: delta review, 1 thread, approved 10:45, re-approved 14:01 and 14:44 after pushes

Analysis and notes
- <topic>: <outcome in one line>

Other
- <other project>: <what>
- local, not pushed: <hash> <title> (<branch>)

Not reached: <source> (<why>)
```

**Week** — the same sources over the whole range, shorter per item:

```
Recap for 09.11-15.11.2026: 2 own tickets, 14 requests opened, 1 merged, 21 commits; 12 requests reviewed, 9 threads posted, 17 approvals

Own work
- ABC-101 <what it is> (Mon-Fri): <what was built, 2-4 lines>; at the end of the week: <open / merged, waiting on whom>
- ABC-87 <title> (Tue): <one line>; merged

Reviews
- !96 ABC-140, <author> (Fri): first review, 2 threads, both fixed, approved
- re-approvals after pushes: !44 x3, !29, !49

Analysis and notes
- <topic> (Thu-Fri): <outcome>

By day
- Mon 09.11: <2-3 headline items>
- Tue 10.11: …

Not reached: …
```

Week rules: one item per ticket with the days it was worked on and its state at the end of the range;
the number of commits and what they delivered, not a list of them; one line per reviewed request, a
thread's point only when it is blocking or still open; "By day" is an index of the same items, days
without activity left out.

**Both modes**

- A thread is identified by the request, `path/to/File.kt:line` and its point — never by an internal id.
- A request is its number, the ticket key and the author; a commit is its title, the hash only for
  unpushed ones.
- Repeated approvals of one request are one line; the totals count approval events.
- A finding that was made and deliberately not posted is "found, not posted", not a posted thread.
- An empty section is left out. No tables: the report is pasted into chats and terminals.
- No verdict on productivity, no advice, no plan for the next day unless asked.

## Step 8 — A text for the team (`--standup` or when asked)

After the recap, a short text the person can say or paste as their own, in `standup_language`: 3–6 lines
for a day, 5–10 for a week. What was done, by ticket key and the name people see in the tracker. No
class, method or flag names, no thread counts, no word about how the list was built. It is not sent
anywhere.
