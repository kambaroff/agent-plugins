import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recap.py"


def load():
    spec = importlib.util.spec_from_file_location("recap", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


recap = load()
PLUS5 = timezone(timedelta(hours=5))
WORKWEEK = [1, 2, 3, 4, 5]


def run_main(*args):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = recap.main(list(args))
    return code, out.getvalue(), err.getvalue()


class PeriodTest(unittest.TestCase):
    def period(self, arg, today, workdays=WORKWEEK):
        return recap.resolve_period(arg, today, workdays)

    def test_default_on_monday_is_friday(self):
        self.assertEqual(self.period(None, date(2026, 11, 16)), ("day", date(2026, 11, 13), date(2026, 11, 13)))

    def test_default_midweek_is_yesterday(self):
        self.assertEqual(self.period("day", date(2026, 11, 18)), ("day", date(2026, 11, 17), date(2026, 11, 17)))

    def test_default_on_sunday_is_friday(self):
        self.assertEqual(self.period(None, date(2026, 11, 15))[1], date(2026, 11, 13))

    def test_workdays_can_include_saturday(self):
        self.assertEqual(self.period(None, date(2026, 11, 16), [1, 2, 3, 4, 5, 6])[1], date(2026, 11, 14))

    def test_week_is_the_last_completed_monday_to_sunday(self):
        for today in (date(2026, 11, 16), date(2026, 11, 19), date(2026, 11, 22)):
            self.assertEqual(self.period("week", today), ("week", date(2026, 11, 9), date(2026, 11, 15)))

    def test_this_week_runs_from_monday_through_today(self):
        self.assertEqual(self.period("this-week", date(2026, 11, 18)), ("week", date(2026, 11, 16), date(2026, 11, 18)))

    def test_weekday_name_is_the_most_recent_one_before_today(self):
        self.assertEqual(self.period("friday", date(2026, 11, 16))[1], date(2026, 11, 13))
        self.assertEqual(self.period("mon", date(2026, 11, 16))[1], date(2026, 11, 9))

    def test_dates(self):
        today = date(2026, 11, 16)
        self.assertEqual(self.period("2026-11-13", today)[1], date(2026, 11, 13))
        self.assertEqual(self.period("13.11", today)[1], date(2026, 11, 13))
        self.assertEqual(self.period("13.11.2025", today)[1], date(2025, 11, 13))

    def test_day_and_month_in_the_future_mean_last_year(self):
        self.assertEqual(self.period("24.12", date(2026, 11, 16))[1], date(2025, 12, 24))

    def test_range(self):
        self.assertEqual(
            self.period("2026-11-09..2026-11-13", date(2026, 11, 16)),
            ("week", date(2026, 11, 9), date(2026, 11, 13)),
        )
        self.assertEqual(self.period("13.11..13.11", date(2026, 11, 16))[0], "day")

    def test_bad_input(self):
        for arg in ("someday", "2026-13-40", "2026-11-13..2026-11-09"):
            with self.assertRaises(recap.BadInput):
                self.period(arg, date(2026, 11, 16))
        for text in ("", "0", "1,8", "a"):
            with self.assertRaises(recap.BadInput):
                recap.parse_workdays(text)


class WindowTest(unittest.TestCase):
    def test_bounds_follow_the_local_day_not_the_utc_date(self):
        w = recap.window(None, date(2026, 11, 16), WORKWEEK, PLUS5)
        self.assertEqual(w["label"], "Fri 13.11.2026")
        self.assertEqual((w["start_utc"], w["end_utc"]), ("2026-11-12T19:00:00Z", "2026-11-13T19:00:00Z"))
        self.assertEqual((w["feed_after"], w["feed_before"]), ("2026-11-11", "2026-11-14"))
        self.assertEqual(w["tz"], "+05:00")

    def test_feed_dates_cover_a_zone_west_of_utc(self):
        w = recap.window("2026-11-13", date(2026, 11, 16), WORKWEEK, recap.parse_tz("-08:00"))
        self.assertEqual((w["start_utc"], w["end_utc"]), ("2026-11-13T08:00:00Z", "2026-11-14T08:00:00Z"))
        self.assertEqual((w["feed_after"], w["feed_before"]), ("2026-11-12", "2026-11-15"))

    def test_week_window(self):
        w = recap.window("week", date(2026, 11, 16), WORKWEEK, PLUS5)
        self.assertEqual((w["mode"], w["days"], w["label"]), ("week", 7, "09.11-15.11.2026"))
        self.assertEqual((w["start_utc"], w["end_utc"]), ("2026-11-08T19:00:00Z", "2026-11-15T19:00:00Z"))

    def test_time_zones(self):
        self.assertIsNone(recap.parse_tz(None))
        self.assertIsNone(recap.parse_tz("local"))
        self.assertEqual(recap.parse_tz("UTC"), timezone.utc)
        self.assertEqual(recap.parse_tz("+0530").utcoffset(None), timedelta(hours=5, minutes=30))
        self.assertEqual(recap.parse_tz("-3").utcoffset(None), timedelta(hours=-3))
        for bad in ("+99:00", "Nowhere/Land"):
            with self.assertRaises(recap.BadInput):
                recap.parse_tz(bad)

    def test_named_zone_changes_offset_with_daylight_saving(self):
        try:
            zone = recap.parse_tz("Europe/Berlin")
        except recap.BadInput:
            self.skipTest("no IANA time zone data on this machine")
        summer = recap.window("2026-07-01", date(2026, 11, 16), WORKWEEK, zone)
        winter = recap.window("2026-12-01", date(2026, 12, 16), WORKWEEK, zone)
        self.assertEqual((summer["tz"], summer["start_utc"]), ("+02:00", "2026-06-30T22:00:00Z"))
        self.assertEqual((winter["tz"], winter["start_utc"]), ("+01:00", "2026-11-30T23:00:00Z"))

    def test_main_prints_json(self):
        code, out, _ = run_main("window", "week", "--today", "2026-11-16", "--tz", "+05:00", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["first"], "2026-11-09")

    def test_main_reports_bad_input_with_exit_2(self):
        code, out, err = run_main("window", "someday")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("not a date", err)


def gitlab_push(at, ref, title, count=1):
    return {
        "project_id": 7,
        "action_name": "pushed to",
        "created_at": at,
        "push_data": {"action": "pushed", "ref": ref, "ref_type": "branch", "commit_count": count, "commit_title": title},
    }


def gitlab_note(at, iid, body, path=None, line=None, old=False):
    position = None
    if path:
        position = {"old_path": path, "old_line": line} if old else {"new_path": path, "new_line": line}
    return {
        "project_id": 7,
        "action_name": "commented on",
        "created_at": at,
        "target_type": "DiffNote" if path else "Note",
        "target_title": f"Title of {iid}",
        "note": {"noteable_type": "MergeRequest", "noteable_iid": iid, "body": body, "position": position},
    }


def gitlab_mr(at, iid, action):
    return {
        "project_id": 7,
        "action_name": action,
        "created_at": at,
        "target_type": "MergeRequest",
        "target_iid": iid,
        "target_title": f"Title of {iid}",
    }


GITLAB = [
    gitlab_mr("2026-11-13T09:44:00.000Z", 44, "approved"),
    gitlab_mr("2026-11-13T09:01:00.000Z", 44, "approved"),
    gitlab_note("2026-11-13T05:32:10.120Z", 44, "\n  The fallback   is gone here.\nSecond line.", "app/Main.kt", 101),
    gitlab_mr("2026-11-13T05:45:00.000Z", 44, "approved"),
    gitlab_note("2026-11-13T06:20:00.000Z", 77, "Fixed — naïve check removed", "app/Old.kt", 7, old=True),
    gitlab_note("2026-11-13T06:21:00.000Z", 77, "General reply"),
    gitlab_push("2026-11-13T05:29:00.000Z", "feature/a", "fix: lowercase path"),
    gitlab_push("2026-11-13T05:30:00.000Z", "feature/b", "Merge branch 'feature/a' into feature/b", 2),
    gitlab_push("2026-11-13T05:31:00.000Z", "feature/c", "Merge branch 'feature/b' into feature/c", 3),
    gitlab_mr("2026-11-13T07:00:00.000Z", 60, "opened"),
    gitlab_mr("2026-11-13T08:00:00.000Z", 60, "accepted"),
    {"project_id": 9, "action_name": "deleted", "created_at": "2026-11-13T10:00:00Z", "target_type": None,
     "push_data": None, "target_title": None},
    gitlab_note("2026-11-12T18:59:59.000Z", 50, "the evening before, outside the window", "a.kt", 1),
    gitlab_mr("2026-11-13T19:00:00.000Z", 51, "approved"),
]
START = datetime(2026, 11, 12, 19, tzinfo=timezone.utc)
END = datetime(2026, 11, 13, 19, tzinfo=timezone.utc)


class GitlabFeedTest(unittest.TestCase):
    def setUp(self):
        self.result = recap.digest(GITLAB, "gitlab", START, END)
        self.text = recap.render_feed(self.result, PLUS5, False)

    def test_events_outside_the_local_window_are_dropped(self):
        self.assertEqual(self.result["totals"]["events"], 12)
        self.assertNotIn("!50", self.text)
        self.assertNotIn("!51", self.text)

    def test_totals(self):
        self.assertEqual(
            self.result["totals"],
            {"events": 12, "pushes": 1, "merge_pushes": 2, "comments": 3, "approvals": 3, "approved_targets": 1,
             "opened": 1, "merged": 1},
        )

    def test_repeated_approvals_are_one_line_in_time_order(self):
        self.assertIn("    approved 10:45, 14:01, 14:44 (3 times)", self.text)
        self.assertEqual(self.text.count("approved 1"), 1)

    def test_comment_has_path_line_and_first_line_of_the_body(self):
        self.assertIn("    10:32 comment app/Main.kt:101 | The fallback is gone here.", self.text)
        self.assertNotIn("Second line", self.text)

    def test_comment_on_a_removed_line_uses_the_old_side(self):
        self.assertIn("    11:20 comment app/Old.kt:7 | Fixed — naïve check removed", self.text)

    def test_comment_without_a_position_is_general(self):
        self.assertIn("    11:21 comment general | General reply", self.text)

    def test_merge_pushes_are_folded_into_one_line(self):
        self.assertIn("    10:29 feature/a: 1 commit, last: fix: lowercase path", self.text)
        self.assertIn("    10:30..10:31 2 merge pushes: feature/b, feature/c", self.text)

    def test_opened_and_merged(self):
        block = self.text.split("  !60 Title of 60\n")[1]
        self.assertTrue(block.startswith("    12:00 opened\n    13:00 merged\n"))

    def test_events_are_grouped_by_project(self):
        self.assertEqual([g["project"] for g in self.result["groups"]], ["project 7", "project 9"])
        self.assertIn("project 9\n  15:00 deleted", self.text)

    def test_long_body_is_cut(self):
        result = recap.digest([gitlab_note("2026-11-13T06:00:00Z", 1, "x" * 500)], "gitlab", START, END, cap=40)
        body = result["groups"][0]["targets"][0]["events"][0]["body"]
        self.assertEqual(len(body), 40)
        self.assertTrue(body.endswith("…"))

    def test_several_days_show_the_date(self):
        text = recap.render_feed(self.result, PLUS5, True)
        self.assertIn("    11-13 10:32 comment app/Main.kt:101", text)


GITHUB = [
    {"type": "PushEvent", "created_at": "2026-11-13T08:00:00Z", "repo": {"name": "me/tool"},
     "payload": {"ref": "refs/heads/fix/windows", "size": 2,
                 "commits": [{"message": "first"}, {"message": "write bytes, not text\n\nbody"}]}},
    {"type": "PushEvent", "created_at": "2026-11-13T08:05:00Z", "repo": {"name": "me/tool"},
     "payload": {"ref": "refs/heads/main"}},
    {"type": "PullRequestEvent", "created_at": "2026-11-13T08:10:00Z", "repo": {"name": "lead/tool"},
     "payload": {"action": "opened", "number": 8, "pull_request": {"number": 8, "title": "Windows fixes"}}},
    {"type": "PullRequestEvent", "created_at": "2026-11-13T09:10:00Z", "repo": {"name": "lead/tool"},
     "payload": {"action": "closed", "number": 8, "pull_request": {"number": 8, "merged": True}}},
    {"type": "PullRequestReviewEvent", "created_at": "2026-11-13T09:20:00Z", "repo": {"name": "lead/tool"},
     "payload": {"review": {"state": "approved"}, "pull_request": {"number": 11}}},
    {"type": "PullRequestReviewEvent", "created_at": "2026-11-13T09:21:00Z", "repo": {"name": "lead/tool"},
     "payload": {"review": {"state": "changes_requested"}, "pull_request": {"number": 12}}},
    {"type": "PullRequestReviewCommentEvent", "created_at": "2026-11-13T09:30:00Z", "repo": {"name": "lead/tool"},
     "payload": {"comment": {"path": "scripts/run.py", "line": None, "original_line": 31, "body": "Done in abc1234"},
                 "pull_request": {"number": 8}}},
    {"type": "IssueCommentEvent", "created_at": "2026-11-13T09:40:00Z", "repo": {"name": "lead/tool"},
     "payload": {"issue": {"number": 8, "title": "Windows fixes"}, "comment": {"body": "Rebased onto next"}}},
    {"type": "CreateEvent", "created_at": "2026-11-13T07:59:00Z", "repo": {"name": "me/tool"},
     "payload": {"ref": "fix/windows", "ref_type": "branch"}},
    {"type": "WatchEvent", "created_at": "2026-11-10T07:59:00Z", "repo": {"name": "x/y"}, "payload": {"action": "started"}},
]


class GithubFeedTest(unittest.TestCase):
    def setUp(self):
        self.result = recap.digest(GITHUB, "github", START, END)
        self.text = recap.render_feed(self.result, timezone.utc, False)

    def test_totals(self):
        t = self.result["totals"]
        self.assertEqual((t["events"], t["pushes"], t["comments"], t["approvals"], t["opened"], t["merged"]),
                         (9, 2, 2, 1, 1, 1))

    def test_push_with_and_without_commits_in_the_payload(self):
        self.assertIn("    08:00 fix/windows: 2 commits, last: write bytes, not text", self.text)
        self.assertIn("    08:05 main: pushed", self.text)

    def test_pull_request_lines(self):
        block = self.text.split("  #8 Windows fixes\n")[1]
        self.assertTrue(block.startswith(
            "    08:10 opened\n    09:10 merged\n    09:30 comment scripts/run.py:31 | Done in abc1234\n"
            "    09:40 comment general | Rebased onto next\n"
        ))

    def test_reviews(self):
        self.assertIn("  #11\n    approved 09:20\n", self.text)
        self.assertIn("  #12\n    09:21 changes requested\n", self.text)

    def test_other_events(self):
        self.assertIn("me/tool\n  pushes\n", self.text)
        self.assertIn("  07:59 Create branch fix/windows", self.text)


class FeedInputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.write_bytes(text.encode("utf-8"))
        return str(path)

    def feed(self, *files, forge="gitlab"):
        return run_main("feed", "--forge", forge, "--start", "2026-11-12T19:00:00Z", "--end", "2026-11-13T19:00:00Z",
                        "--tz", "+05:00", *files)

    def test_pages_written_one_after_another_are_all_read(self):
        path = self.write("events.json", json.dumps(GITLAB[:3]) + "\n" + json.dumps(GITLAB[3:]))
        code, out, _ = self.feed(path)
        self.assertEqual(code, 0)
        self.assertIn("3 approvals on 1 targets", out)

    def test_several_files_and_a_byte_order_mark(self):
        first = self.write("a.json", "﻿" + json.dumps(GITLAB[:6]))
        second = self.write("b.json", json.dumps(GITLAB[6:]))
        code, out, _ = self.feed(first, second)
        self.assertEqual(code, 0)
        self.assertIn("1 pushes, 2 merge pushes, 3 comments", out)

    def test_no_events_in_the_window_is_exit_1(self):
        code, out, _ = self.feed(self.write("events.json", json.dumps(GITLAB[-2:])))
        self.assertEqual(code, 1)
        self.assertIn("totals: 0 pushes", out)

    def test_bad_input_is_exit_2(self):
        broken = self.write("broken.json", "[{")
        empty_time = self.write("time.json", json.dumps([{"created_at": "yesterday"}]))
        for args in ((broken,), (empty_time,), (str(self.dir / "missing.json"),)):
            code, out, err = self.feed(*args)
            self.assertEqual((code, out), (2, ""), args)
            self.assertTrue(err.startswith("recap: "), err)
        code, _, err = run_main("feed", "--forge", "gitlab", "--start", "2026-11-13T19:00:00Z",
                                "--end", "2026-11-12T19:00:00Z", broken)
        self.assertEqual(code, 2)
        self.assertIn("earlier", err)

    def test_json_output(self):
        code, out, _ = run_main("feed", "--forge", "github", "--start", "2026-11-12T19:00:00Z",
                                "--end", "2026-11-13T19:00:00Z", "--json", self.write("gh.json", json.dumps(GITHUB)))
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["totals"]["events"], 9)
        self.assertEqual(data["groups"][0]["pushes"][0]["when"], "2026-11-13T08:00:00Z")

    def test_timestamps_with_offsets(self):
        for text, hour in (("2026-11-13T10:27:08.000+05:00", 5), ("2026-11-13T05:27:08Z", 5),
                           ("2026-11-13T05:27:08.123456+0000", 5), ("2026-11-13 05:27:08", 5)):
            self.assertEqual(recap.parse_time(text).hour, hour, text)

    def test_output_survives_a_legacy_console_encoding(self):
        path = self.write("events.json", json.dumps(GITLAB))
        env = dict(os.environ, PYTHONIOENCODING="cp1251")
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "feed", "--forge", "gitlab", "--start", "2026-11-12T19:00:00Z",
             "--end", "2026-11-13T19:00:00Z", "--tz", "+05:00", path],
            capture_output=True, env=env,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Fixed — naïve check removed", done.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
