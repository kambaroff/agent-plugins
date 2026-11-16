---
# work-recap — default config
# Copy the keys you need into one of:
#   ~/.claude/work-recap.md               — user-level
#   .claude/work-recap.local.md           — project-level, wins key by key (keep it out of git)
forge:
timezone: local
workdays: 1,2,3,4,5
repos:
notes:
extra:
language:
standup_language:
---

# work-recap config

Neither file lives inside the plugin, so updating it never touches your settings. Each key resolves
separately: project file → user file → the defaults above.

## Keys

**`forge`** — `gitlab` or `github`. Empty: by the `origin` remote of the repository `/recap` runs in.

**`timezone`** — the zone a "day" is counted in: an IANA name (`Europe/Berlin`), an offset (`+05:00`),
or `local` (default) for the machine's zone. On Windows without IANA data use an offset.

**`workdays`** — ISO weekday numbers that count as work days, `1,2,3,4,5` by default. `/recap` with no
period steps back over the others.

**`repos`** — more local clones whose history is yours to report, comma-separated paths. The repository
`/recap` runs in is always included.

**`notes`** — a glob of files written during the work, with the date in the name
(`~/notes/handoff-*.md`, `docs/reviews/*.md`). The ones dated inside the period are read for what the
forge does not record: unposted findings, decisions, manual checks.

**`extra`** — free-form instructions for other sources, read-only: "tracker changes through the
`tracker` MCP server: issues I changed in the period", "pull requests in `org/tools` on GitHub too".

**`language`** — the language of the recap. Empty: the language the person writes in.

**`standup_language`** — the language of the text for the team (`--standup`). Empty: same as `language`.
