#!/usr/bin/env python3
"""Pull a fresh `uiautomator dump` from the device, or wait until a screen is ready.

Usage:
    ui-dump.py <out.xml> [--serial <serial>] [--retries <n>]
               [--until <text> | --gone <text>] [--exact] [--timeout <s>] [--interval <s>]

The dump on the device is deleted before every attempt: `uiautomator dump`
exits 0 even when it wrote nothing (`could not get idle state` on an animated
screen), and a pull would then bring back the screen of an earlier step. A
failed attempt is repeated up to `--retries` times (3 by default).

`--until` repeats the dump until a node matches the text, `--gone` until none
does (a loader that should disappear); matching is the one of `ui-nodes.py
--find`. Both give up after `--timeout` seconds (15 by default). On success
`--until` prints the matching nodes as `ui-nodes.py` does.

Exit code: 0 when a dump was pulled and the condition holds, 1 when the
condition still did not hold at the timeout (the last dump stays at
<out.xml>), 2 when no dump could be taken.
"""
import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

DEVICE_PATH = "/sdcard/ui.xml"


def load_ui_nodes():
    spec = importlib.util.spec_from_file_location("ui_nodes", Path(__file__).with_name("ui-nodes.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ui_nodes = load_ui_nodes()


def adb(serial, *args):
    command = ["adb", *(["-s", serial] if serial else []), *args]
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")


def output(result):
    return (result.stdout + result.stderr).strip()


def dump_once(serial, out):
    if out.exists():
        out.unlink()
    adb(serial, "shell", "rm", "-f", DEVICE_PATH)
    dumped = adb(serial, "shell", "uiautomator", "dump", DEVICE_PATH)
    pulled = adb(serial, "pull", DEVICE_PATH, str(out))
    if pulled.returncode == 0 and out.is_file():
        return None
    return output(dumped) or output(pulled) or "nothing was written"


def dump(serial, out, retries, pause):
    error = None
    for attempt in range(max(1, retries)):
        if attempt:
            time.sleep(pause)
        error = dump_once(serial, out)
        if error is None:
            return None
    return error


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--serial")
    ap.add_argument("--retries", type=int, default=3)
    condition = ap.add_mutually_exclusive_group()
    condition.add_argument("--until")
    condition.add_argument("--gone")
    ap.add_argument("--exact", action="store_true")
    ap.add_argument("--timeout", type=float, default=15)
    ap.add_argument("--interval", type=float, default=1)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    needle = a.until or a.gone
    deadline = time.monotonic() + a.timeout
    while True:
        error = dump(a.serial, out, a.retries, a.interval)
        if error is not None:
            print(f"no dump from the device: {error}", file=sys.stderr)
            return 2
        if needle is None:
            return 0
        try:
            found = [n for n in ui_nodes.read(out) if ui_nodes.matches(n, needle, a.exact)]
        except ui_nodes.READ_ERRORS as error:
            print(f"cannot read {out}: {error}", file=sys.stderr)
            return 2
        if a.until and found:
            for n in found:
                print(ui_nodes.line(n))
            return 0
        if a.gone and not found:
            return 0
        if time.monotonic() >= deadline:
            state = "did not appear" if a.until else "is still on screen"
            print(f"{needle!r} {state} after {a.timeout:g}s; last dump: {out}", file=sys.stderr)
            return 1
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
