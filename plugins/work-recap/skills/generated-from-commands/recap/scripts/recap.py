#!/usr/bin/env python3
"""Period arithmetic and activity-feed digest for /recap.

Usage:
    recap.py window [<period>] [--tz <zone>] [--workdays <1,2,..>] [--today <YYYY-MM-DD>] [--json]
    recap.py feed --forge <gitlab|github> --start <utc> --end <utc> [--tz <zone>]
                  [--body <n>] [--json] <events.json>...

window prints the period in local dates, its bounds in UTC and the dates to
pass to the forge's activity feed. <period> is one of:
    (nothing), day     the previous work day (weekends are stepped over)
    today
    week               the last completed week, Monday to Sunday
    this-week          Monday of the current week through today
    mon .. sun         the most recent such weekday before today
    2026-11-13, 13.11, 13.11.2026
    2026-11-09..2026-11-13

feed reads the JSON the forge's events API returned (GitLab `events`, GitHub
`users/<login>/events`; several pages in one file are fine), keeps the events
inside the window and prints them grouped by project and merge request: pushes,
comments with path:line, approvals, opened / merged / closed.

<zone> is an IANA name (Europe/Berlin), an offset (+05:00) or `local` (default).
Where IANA names are not available (Windows without tzdata) pass an offset.

Exit code: 0; 1 when feed finds no events inside the window; 2 on bad input.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FULL_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MERGE_TITLE = re.compile(r"^Merge (branch|remote-tracking branch|pull request|tag) ")


class BadInput(Exception):
    pass


def parse_tz(name):
    """None for the system's local zone, otherwise a tzinfo."""
    if name is None or name.strip().lower() in ("", "local"):
        return None
    text = name.strip()
    if text.upper() in ("UTC", "Z"):
        return timezone.utc
    m = re.fullmatch(r"([+-])(\d{1,2})(?::?(\d{2}))?", text)
    if m:
        minutes = int(m.group(2)) * 60 + int(m.group(3) or 0)
        if minutes > 14 * 60:
            raise BadInput(f"offset out of range: {name}")
        return timezone(timedelta(minutes=minutes if m.group(1) == "+" else -minutes))
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(text)
    except Exception:
        raise BadInput(f"unknown time zone {name!r}: pass an offset such as +05:00")


def local_midnight_utc(day, tz):
    if tz is None:
        return datetime(day.year, day.month, day.day).astimezone().astimezone(timezone.utc)
    return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)


def offset_label(day, tz):
    if tz is None:
        offset = datetime(day.year, day.month, day.day, 12).astimezone().utcoffset()
    else:
        offset = datetime(day.year, day.month, day.day, 12, tzinfo=tz).utcoffset()
    minutes = int((offset or timedelta(0)).total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def parse_day(text, today):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            raise BadInput(f"not a date: {text}")
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", text)
    if m:
        try:
            if m.group(3):
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            day = date(today.year, int(m.group(2)), int(m.group(1)))
            return day if day <= today else date(today.year - 1, day.month, day.day)
        except ValueError:
            raise BadInput(f"not a date: {text}")
    raise BadInput(f"not a date: {text}")


def parse_workdays(text):
    try:
        days = sorted({int(part) for part in text.split(",") if part.strip()})
    except ValueError:
        raise BadInput(f"workdays are ISO weekday numbers 1-7, got {text!r}")
    if not days or days[0] < 1 or days[-1] > 7:
        raise BadInput(f"workdays are ISO weekday numbers 1-7, got {text!r}")
    return days


def resolve_period(arg, today, workdays):
    """(mode, first, last) in local dates; mode is day or week."""
    text = (arg or "day").strip().lower()
    if text in ("day", "yesterday", "prev", "previous"):
        day = today - timedelta(days=1)
        while day.isoweekday() not in workdays:
            day -= timedelta(days=1)
        return "day", day, day
    if text == "today":
        return "day", today, today
    monday = today - timedelta(days=today.weekday())
    if text in ("week", "last-week", "weekly"):
        return "week", monday - timedelta(days=7), monday - timedelta(days=1)
    if text == "this-week":
        return "week", monday, today
    if text in WEEKDAYS or text in FULL_WEEKDAYS:
        back = (today.weekday() - WEEKDAYS.index(text[:3])) % 7 or 7
        day = today - timedelta(days=back)
        return "day", day, day
    if ".." in text:
        left, _, right = text.partition("..")
        first, last = parse_day(left.strip(), today), parse_day(right.strip(), today)
        if first > last:
            raise BadInput(f"the range ends before it starts: {arg}")
        return ("day" if first == last else "week"), first, last
    day = parse_day(text, today)
    return "day", day, day


def window(arg, today, workdays, tz):
    mode, first, last = resolve_period(arg, today, workdays)
    start = local_midnight_utc(first, tz)
    end = local_midnight_utc(last + timedelta(days=1), tz)
    if first == last:
        label = f"{WEEKDAYS[first.weekday()].capitalize()} {first:%d.%m.%Y}"
    else:
        label = f"{first:%d.%m}-{last:%d.%m.%Y}"
    return {
        "mode": mode,
        "label": label,
        "first": first.isoformat(),
        "last": last.isoformat(),
        "days": (last - first).days + 1,
        "tz": offset_label(first, tz),
        "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feed_after": (start.date() - timedelta(days=1)).isoformat(),
        "feed_before": (end.date() + timedelta(days=1)).isoformat(),
    }


def render_window(w):
    return "\n".join(
        [
            f"period: {w['label']} ({w['mode']}, {w['days']} day{'s' if w['days'] != 1 else ''})",
            f"local:  {w['first']} .. {w['last']}  tz {w['tz']}",
            f"utc:    {w['start_utc']} .. {w['end_utc']}",
            f"feed:   after={w['feed_after']} before={w['feed_before']}",
        ]
    )


def parse_time(text):
    """An ISO 8601 timestamp from a forge, as an aware UTC datetime."""
    if not isinstance(text, str):
        raise BadInput(f"not a timestamp: {text!r}")
    value = re.sub(r"\.\d+", "", text.strip())
    value = re.sub(r"[zZ]$", "+00:00", value)
    value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise BadInput(f"not a timestamp: {text!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_events(text):
    """Events from one file: a JSON array, or several arrays written one after another."""
    decoder = json.JSONDecoder()
    events, pos = [], 0
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return events
        try:
            value, pos = decoder.raw_decode(text, pos)
        except ValueError as error:
            raise BadInput(f"not JSON: {error}")
        if isinstance(value, list):
            events += [item for item in value if isinstance(item, dict)]
        elif isinstance(value, dict):
            events.append(value)


def first_line(text, cap):
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        line = " ".join(line.split())
        if line:
            return line if len(line) <= cap else line[: cap - 1].rstrip() + "…"
    return ""


def from_gitlab(e, cap):
    record = {
        "when": parse_time(e.get("created_at")),
        "project": f"project {e.get('project_id')}" if e.get("project_id") is not None else "",
        "target": None,
        "title": e.get("target_title") or "",
    }
    push, note = e.get("push_data"), e.get("note")
    action = (e.get("action_name") or "").strip()
    if push:
        title = push.get("commit_title") or ""
        record.update(
            kind="push",
            branch=push.get("ref") or "",
            commits=push.get("commit_count"),
            title=title,
            merge=bool(MERGE_TITLE.match(title)),
            action=push.get("action") or action,
        )
    elif note:
        kind = note.get("noteable_type") or e.get("target_type") or ""
        number = note.get("noteable_iid")
        position = note.get("position") or {}
        record.update(
            kind="comment",
            target=f"{'!' if kind == 'MergeRequest' else '#'}{number}" if number is not None else kind,
            path=position.get("new_path") or position.get("old_path"),
            line=position.get("new_line") or position.get("old_line"),
            body=first_line(note.get("body"), cap),
        )
    elif e.get("target_type") == "MergeRequest":
        kinds = {"accepted": "merged", "opened": "opened", "closed": "closed", "reopened": "reopened",
                 "approved": "approved", "unapproved": "unapproved"}
        record.update(kind=kinds.get(action, "other"), target=f"!{e.get('target_iid')}")
        if record["kind"] == "other":
            record["text"] = action
    else:
        record.update(kind="other", text=" ".join(x for x in (action, e.get("target_type") or "", record["title"]) if x))
    return record


def from_github(e, cap):
    payload = e.get("payload") or {}
    pull = payload.get("pull_request") or {}
    record = {
        "when": parse_time(e.get("created_at")),
        "project": (e.get("repo") or {}).get("name") or "",
        "target": None,
        "title": pull.get("title") or "",
    }
    kind = e.get("type") or ""
    number = pull.get("number") or payload.get("number")
    if kind == "PushEvent":
        commits = payload.get("commits") or []
        title = first_line(commits[-1].get("message"), 200) if commits else ""
        record.update(
            kind="push",
            branch=re.sub(r"^refs/heads/", "", payload.get("ref") or ""),
            commits=payload.get("size", len(commits) or None),
            title=title,
            merge=bool(MERGE_TITLE.match(title)),
            action="pushed",
        )
    elif kind == "PullRequestEvent":
        action = payload.get("action") or ""
        if action == "closed" and pull.get("merged"):
            action = "merged"
        known = action in ("opened", "closed", "reopened", "merged")
        record.update(kind=action if known else "other", target=f"#{number}")
        if not known:
            record["text"] = action
    elif kind == "PullRequestReviewEvent":
        state = ((payload.get("review") or {}).get("state") or "").lower()
        kinds = {"approved": "approved", "changes_requested": "changes requested"}
        record.update(kind=kinds.get(state, "review"), target=f"#{number}")
    elif kind == "PullRequestReviewCommentEvent":
        comment = payload.get("comment") or {}
        record.update(
            kind="comment",
            target=f"#{number}",
            path=comment.get("path"),
            line=comment.get("line") or comment.get("original_line"),
            body=first_line(comment.get("body"), cap),
        )
    elif kind == "IssueCommentEvent":
        issue = payload.get("issue") or {}
        record.update(
            kind="comment",
            target=f"#{issue.get('number')}",
            title=issue.get("title") or "",
            path=None,
            line=None,
            body=first_line((payload.get("comment") or {}).get("body"), cap),
        )
    else:
        ref = payload.get("ref")
        words = [re.sub(r"Event$", "", kind), payload.get("action") or "", payload.get("ref_type") or "", ref or ""]
        record.update(kind="other", text=" ".join(x for x in words if x))
    return record


def digest(events, forge, start, end, cap=160):
    convert = from_gitlab if forge == "gitlab" else from_github
    records = []
    for e in events:
        if not e.get("created_at"):
            continue
        record = convert(e, cap)
        if start <= record["when"] < end:
            records.append(record)
    records.sort(key=lambda r: r["when"])

    groups = {}
    for r in records:
        group = groups.setdefault(r["project"], {"project": r["project"], "targets": {}, "pushes": [], "other": []})
        if r["kind"] == "push":
            group["pushes"].append(r)
        elif r["target"] is None or r["kind"] == "other" and not str(r["target"]).startswith(("!", "#")):
            group["other"].append(r)
        else:
            target = group["targets"].setdefault(r["target"], {"target": r["target"], "title": "", "events": []})
            target["title"] = target["title"] or r["title"]
            target["events"].append(r)

    def count(kind):
        return sum(1 for r in records if r["kind"] == kind)

    pushes = [r for r in records if r["kind"] == "push"]
    totals = {
        "events": len(records),
        "pushes": sum(1 for r in pushes if not r["merge"]),
        "merge_pushes": sum(1 for r in pushes if r["merge"]),
        "comments": count("comment"),
        "approvals": count("approved"),
        "approved_targets": len({(r["project"], r["target"]) for r in records if r["kind"] == "approved"}),
        "opened": count("opened"),
        "merged": count("merged"),
    }
    return {"totals": totals, "groups": [dict(g, targets=list(g["targets"].values())) for g in groups.values()]}


def render_feed(result, tz, several_days):
    def at(when):
        local = when.astimezone(tz)
        return local.strftime("%m-%d %H:%M" if several_days else "%H:%M")

    out = []
    for group in result["groups"]:
        out.append(group["project"] or "(no project)")
        for target in group["targets"]:
            out.append(f"  {target['target']} {target['title']}".rstrip())
            approvals = [at(r["when"]) for r in target["events"] if r["kind"] == "approved"]
            for r in target["events"]:
                if r["kind"] == "comment":
                    place = f"{r['path']}:{r['line']}" if r.get("path") else "general"
                    out.append(f"    {at(r['when'])} comment {place} | {r['body']}")
                elif r["kind"] == "other":
                    out.append(f"    {at(r['when'])} {r.get('text', '')}".rstrip())
                elif r["kind"] != "approved":
                    out.append(f"    {at(r['when'])} {r['kind']}")
            if approvals:
                extra = f" ({len(approvals)} times)" if len(approvals) > 1 else ""
                out.append(f"    approved {', '.join(approvals)}{extra}")
        plain = [r for r in group["pushes"] if not r["merge"]]
        merges = [r for r in group["pushes"] if r["merge"]]
        if group["pushes"]:
            out.append("  pushes")
        for r in plain:
            size = f"{r['commits']} commit{'s' if r['commits'] != 1 else ''}" if r["commits"] is not None else r["action"]
            last = f", last: {r['title']}" if r["title"] else ""
            out.append(f"    {at(r['when'])} {r['branch']}: {size}{last}")
        if merges:
            branches = []
            for r in merges:
                if r["branch"] not in branches:
                    branches.append(r["branch"])
            out.append(
                f"    {at(merges[0]['when'])}..{at(merges[-1]['when'])} {len(merges)} merge "
                f"push{'es' if len(merges) != 1 else ''}: {', '.join(branches)}"
            )
        for r in group["other"]:
            out.append(f"  {at(r['when'])} {r.get('text') or r['kind']}")
    t = result["totals"]
    out.append(
        f"totals: {t['pushes']} pushes, {t['merge_pushes']} merge pushes, {t['comments']} comments, "
        f"{t['approvals']} approvals on {t['approved_targets']} targets, {t['opened']} opened, {t['merged']} merged"
    )
    return "\n".join(out)


def jsonable(result):
    def clean(record):
        return dict(record, when=record["when"].strftime("%Y-%m-%dT%H:%M:%SZ"))

    groups = []
    for g in result["groups"]:
        groups.append(
            {
                "project": g["project"],
                "targets": [dict(t, events=[clean(r) for r in t["events"]]) for t in g["targets"]],
                "pushes": [clean(r) for r in g["pushes"]],
                "other": [clean(r) for r in g["other"]],
            }
        )
    return {"totals": result["totals"], "groups": groups}


def main(argv=None):
    for stream, errors in ((sys.stdout, "replace"), (sys.stderr, "backslashreplace")):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors=errors)
    ap = argparse.ArgumentParser(prog="recap.py")
    sub = ap.add_subparsers(dest="command", required=True)
    w = sub.add_parser("window")
    w.add_argument("period", nargs="?")
    w.add_argument("--tz")
    w.add_argument("--workdays", default="1,2,3,4,5")
    w.add_argument("--today")
    w.add_argument("--json", action="store_true")
    f = sub.add_parser("feed")
    f.add_argument("files", nargs="+")
    f.add_argument("--forge", required=True, choices=("gitlab", "github"))
    f.add_argument("--start", required=True)
    f.add_argument("--end", required=True)
    f.add_argument("--tz")
    f.add_argument("--body", type=int, default=160)
    f.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        tz = parse_tz(a.tz)
        if a.command == "window":
            now = datetime.now(tz).date() if tz is not None else date.today()
            today = parse_day(a.today, now) if a.today else now
            result = window(a.period, today, parse_workdays(a.workdays), tz)
            print(json.dumps(result, indent=2) if a.json else render_window(result))
            return 0
        start, end = parse_time(a.start), parse_time(a.end)
        if start >= end:
            raise BadInput("--start must be earlier than --end")
        events = []
        for path in a.files:
            try:
                if path == "-":
                    text = sys.stdin.read()
                else:
                    with open(path, encoding="utf-8-sig", errors="replace") as handle:
                        text = handle.read()
            except OSError as error:
                raise BadInput(f"cannot read {path}: {error}")
            events += load_events(text)
        result = digest(events, a.forge, start, end, max(a.body, 20))
    except BadInput as error:
        print(f"recap: {error}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(jsonable(result), indent=2, ensure_ascii=False))
    else:
        shown = tz if tz is not None else datetime.now().astimezone().tzinfo
        print(render_feed(result, shown, end - start > timedelta(days=1)))
    return 0 if result["totals"]["events"] else 1


if __name__ == "__main__":
    sys.exit(main())
