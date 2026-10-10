#!/usr/bin/env python3
# Copyright (C) 2026 Chris Fettig
# SPDX-License-Identifier: GPL-3.0-or-later
"""Drives the real menu (tui/menu.py) through a pseudo-terminal with a fake valheimctl and checks which commands it ran.
Linux/macOS only (needs pty and curses). Run: python3 tests/pty_menu_test.py"""
import fcntl
import os
import pty
import select
import struct
import sys
import tempfile
import termios
import time

if sys.platform.startswith("win"):
    print("skipped: needs a Unix terminal (pty, curses)")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
MENU = os.path.join(HERE, "..", "tui", "menu.py")

FAKE = r'''#!/usr/bin/env bash
# fake valheimctl for the menu test: logs every call (and what arrived on stdin), prints canned data
echo "CALL $*" >> "$FAKE_LOG"
case "$1 $2 $3" in
  "list --json "*|"list  ") ;;
esac
if [[ "$1" == list && "$*" == *--json* ]]; then
  echo '[{"world":"01","name":"valheim01-Test","game_port":"2010","state":"running","players":"0","memory":"1.2GiB"}]'
elif [[ "$1 $2" == "backups list" ]]; then
  echo '[{"id":"g:20261009-112915","source":"game-auto","created_utc":"2026-10-09 11:29:15","save":"1452","size_kb":"19000","vs_last_restore":"-"},{"id":"s:20261008-220500","source":"snapshot","created_utc":"2026-10-08 22:05:00","save":"?","size_kb":"1500","vs_last_restore":"-"}]'
elif [[ "$1" == passwd ]]; then
  IFS= read -r pw; echo "STDIN-LEN ${#pw}" >> "$FAKE_LOG"; echo "password saved"
else
  echo "ok: $*"
fi
'''

# application-mode arrow keys: what a real terminal sends once curses has enabled the keypad
UP, DOWN, ENTER, ESC = "\x1bOA", "\x1bOB", "\r", "\x1b"


def drain(fd, t=0.05):
    out = b""
    while select.select([fd], [], [], t)[0]:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    return out


def drive(keys, instance_dir, fakebin, log, wait=0.35, timeout=25):
    env = dict(os.environ, VALHEIMCTL_BIN=fakebin, VALHEIMCTL_INSTANCE_DIR=instance_dir, FAKE_LOG=log,
               TERM="xterm", LINES="30", COLUMNS="100", ESCDELAY="25", LC_ALL=os.environ.get("LC_ALL", "C.UTF-8"))
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(instance_dir)
        os.execvpe(sys.executable, [sys.executable, MENU], env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
    time.sleep(0.8)
    drain(fd, 0.3)
    for k in keys:
        os.write(fd, k.encode())
        time.sleep(wait)
        drain(fd)
    end = time.time() + timeout
    status = None
    while time.time() < end:
        drain(fd, 0.1)
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = os.WEXITSTATUS(st) if os.WIFEXITED(st) else -1
            break
    if status is None:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        status = "timeout"
    return status


def calls(log):
    try:
        return [l.rstrip("\n") for l in open(log)]
    except OSError:
        return []


def main():
    tmp = tempfile.mkdtemp()
    fake = os.path.join(tmp, "valheimctl")
    with open(fake, "w") as fh:
        fh.write(FAKE)
    os.chmod(fake, 0o755)
    failures = []

    def check(name, cond, extra=""):
        print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   " + str(extra)))
        if not cond:
            failures.append(name)

    def instance(with_config=True):
        d = tempfile.mkdtemp(dir=tmp)
        if with_config:
            os.makedirs(os.path.join(d, "config", "worlds"))
            os.makedirs(os.path.join(d, "config", "secrets"))
            open(os.path.join(d, "config", "fleet.env"), "w").write("BACKEND=docker\nINSTANCE_ID=main\nPORT_BLOCK=0\n")
            open(os.path.join(d, "config", "worlds", "01.env"), "w").write("SUFFIX=Test\n")
            open(os.path.join(d, "config", "secrets", "default.server.pass"), "w").write("secret1")
        return d

    print("- quit")
    log = os.path.join(tmp, "a.log")
    st = drive(["q"], instance(), fake, log)
    check("q quits with exit 0", st == 0, st)
    check("the world list was read once", any(c == "CALL list --json" for c in calls(log)), calls(log))

    print("- change a world setting with the arrow keys")
    log = os.path.join(tmp, "b.log")
    # Enter opens world 01; Enter on Raids; Down to None; Enter; Esc back to the list; q
    st = drive([ENTER, ENTER, DOWN, ENTER, ESC, "q"], instance(), fake, log)
    check("exit 0", st == 0, st)
    check("Raids = None saved without applying", "CALL set 1 SERVER_ARGS=-modifier raids none --no-apply" in calls(log), calls(log))

    print("- apply the saved change")
    log = os.path.join(tmp, "c.log")
    # open world; change raids; move down to Apply (6 settings below raids: preset, listed, name, admins, extra, then Apply)
    keys = [ENTER, ENTER, DOWN, ENTER] + [DOWN] * 6 + [ENTER, " ", ESC, "q"]
    st = drive(keys, instance(), fake, log)
    check("apply was run with -y", "CALL apply 1 -y" in calls(log), calls(log))

    print("- add a world")
    log = os.path.join(tmp, "d.log")
    # a -> slot dialog (first free = 2) Enter -> name "Fam" Enter -> confirm y -> any key -> q
    st = drive(["a", ENTER, "F", "a", "m", ENTER, "y", " ", "q"], instance(), fake, log)
    check("new world 2 named Fam created non-interactively", "CALL new 2 Fam -y" in calls(log), calls(log))

    print("- remove a world")
    log = os.path.join(tmp, "e.log")
    st = drive(["d", "y", " ", "q"], instance(), fake, log)
    check("remove 1 -y", "CALL remove 1 -y" in calls(log), calls(log))
    log = os.path.join(tmp, "e2.log")
    st = drive(["d", "n", "q"], instance(), fake, log)
    check("answering No removes nothing", not any(c.startswith("CALL remove") for c in calls(log)), calls(log))

    print("- backups and restore")
    log = os.path.join(tmp, "f.log")
    # open world; go down to "Backups and restore..." (the 10th item, 9 steps below Raids)
    keys = [ENTER] + [DOWN] * 9 + [ENTER, ENTER, "y", " ", ESC, ESC, "q"]
    st = drive(keys, instance(), fake, log)
    c = calls(log)
    check("backups list was read", "CALL backups list 1 --json" in c, c)
    check("restore of the newest restore point", "CALL restore 1 g:20261009-112915 -y" in c, c)

    print("- instance settings")
    log = os.path.join(tmp, "g.log")
    # f -> Port block (first item) Enter -> choose 1 (Down) Enter -> Esc -> q
    st = drive(["f", ENTER, DOWN, ENTER, ESC, "q"], instance(), fake, log)
    check("PORT_BLOCK=1 saved via fleet set", "CALL fleet set PORT_BLOCK=1" in calls(log), calls(log))

    print("- first-run setup in an empty directory")
    log = os.path.join(tmp, "h.log")
    d = instance(with_config=False)
    # y create; backend Docker Enter; name Enter (main); password twice; any key not needed; q
    keys = ["y", ENTER, ENTER] + list("secret1") + [ENTER] + list("secret1") + [ENTER, "q"]
    st = drive(keys, d, fake, log, wait=0.25)
    c = calls(log)
    check("init, backend, name and password were set", all(x in c for x in ["CALL init", "CALL fleet set BACKEND=docker", "CALL fleet set INSTANCE_ID=main", "CALL passwd default server"]), c)
    check("password travelled on stdin only (7 characters), never as an argument", "STDIN-LEN 7" in c and not any("secret1" in x for x in c if x.startswith("CALL")), c)

    print()
    print("ALL PASSED" if not failures else "FAILED: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
