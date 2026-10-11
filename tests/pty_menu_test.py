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

    def instance(with_config=True, default_pw=True, own_pw=False, fleet_extra=""):
        d = tempfile.mkdtemp(dir=tmp)
        if with_config:
            os.makedirs(os.path.join(d, "config", "worlds"))
            os.makedirs(os.path.join(d, "config", "secrets"))
            open(os.path.join(d, "config", "fleet.env"), "w").write("BACKEND=docker\nINSTANCE_ID=main\nPORT_BLOCK=0\n" + fleet_extra)
            open(os.path.join(d, "config", "worlds", "01.env"), "w").write("SUFFIX=Test\n")
            if default_pw:
                open(os.path.join(d, "config", "secrets", "default.server.pass"), "w").write("secret1")
            if own_pw:
                open(os.path.join(d, "config", "secrets", "01.server.pass"), "w").write("ownpass1")
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
    # open world; change raids; move down to Apply (7 items below raids: preset, listed, name, password, admins, extra, then Apply)
    keys = [ENTER, ENTER, DOWN, ENTER] + [DOWN] * 7 + [ENTER, " ", ESC, "q"]
    st = drive(keys, instance(), fake, log)
    check("apply was run with -y", "CALL apply 1 -y" in calls(log), calls(log))

    print("- add a world: its join password is its own")
    log = os.path.join(tmp, "d.log")
    # a -> slot (first free = 2) Enter -> name "Fam" Enter -> a shared default exists, so choose: "own" Enter ->
    # password twice -> confirm y -> any key -> q
    keys = ["a", ENTER, "F", "a", "m", ENTER, ENTER] + list("pw1234") + [ENTER] + list("pw1234") + [ENTER, "y", " ", "q"]
    st = drive(keys, instance(), fake, log)
    c = calls(log)
    check("the world's own password was set on stdin", "CALL passwd 2 server" in c and "STDIN-LEN 6" in c, c)
    check("then the world was created non-interactively", "CALL new 2 Fam -y" in c and c.index("CALL passwd 2 server") < c.index("CALL new 2 Fam -y"), c)
    check("the password never appears on a command line", not any("pw1234" in x for x in c if x.startswith("CALL")), c)
    log = os.path.join(tmp, "d2.log")
    st = drive(["a", ENTER, "F", "a", "m", ENTER, DOWN, ENTER, "y", " ", "q"], instance(), fake, log)
    c = calls(log)
    check("choosing the shared default sets no password for the world", "CALL new 2 Fam -y" in c and not any(x.startswith("CALL passwd 2") for x in c), c)
    log = os.path.join(tmp, "d3.log")
    # no shared default exists: there is no choice to make, the world needs its own password straight away
    keys = ["a", ENTER, "F", "a", "m", ENTER] + list("pw1234") + [ENTER] + list("pw1234") + [ENTER, "y", " ", "q"]
    st = drive(keys, instance(default_pw=False), fake, log)
    check("without a shared default the world's own password is required", "CALL passwd 2 server" in calls(log) and "CALL new 2 Fam -y" in calls(log), calls(log))

    print("- change a world's join password")
    log = os.path.join(tmp, "d4.log")
    # open world; down to Join password (4 below Raids); Enter; only "set a new password" is offered; Enter; twice; q
    keys = [ENTER] + [DOWN] * 4 + [ENTER, ENTER] + list("newpw12") + [ENTER] + list("newpw12") + [ENTER, ESC, "q"]
    st = drive(keys, instance(), fake, log)
    check("passwd 1 server with the new password on stdin", "CALL passwd 1 server" in calls(log) and "STDIN-LEN 7" in calls(log), calls(log))
    log = os.path.join(tmp, "d5.log")
    # a world that has its own password can go back to the shared default
    keys = [ENTER] + [DOWN] * 4 + [ENTER, DOWN, ENTER, ESC, "q"]
    st = drive(keys, instance(own_pw=True), fake, log)
    check("a world can return to the shared default", "CALL passwd 1 server --use-default -y" in calls(log), calls(log))

    print("- remove a world")
    log = os.path.join(tmp, "e.log")
    st = drive(["d", "y", " ", "q"], instance(), fake, log)
    check("remove 1 -y", "CALL remove 1 -y" in calls(log), calls(log))
    log = os.path.join(tmp, "e2.log")
    st = drive(["d", "n", "q"], instance(), fake, log)
    check("answering No removes nothing", not any(c.startswith("CALL remove") for c in calls(log)), calls(log))

    print("- backups and restore")
    log = os.path.join(tmp, "f.log")
    # open world; go down to "Backups and restore..." (the 11th item, 10 steps below Raids)
    keys = [ENTER] + [DOWN] * 10 + [ENTER, ENTER, "y", " ", ESC, ESC, "q"]
    st = drive(keys, instance(), fake, log)
    c = calls(log)
    check("backups list was read", "CALL backups list 1 --json" in c, c)
    check("restore of the newest restore point", "CALL restore 1 g:20261009-112915 -y" in c, c)

    print("- instance settings: one 'ports' choice (blocks 0-9 and A)")
    log = os.path.join(tmp, "g.log")
    # f -> Ports (first item) Enter -> Down to block 1 -> Enter -> a world exists, so confirm y -> Esc -> q
    st = drive(["f", ENTER, DOWN, ENTER, "y", ESC, "q"], instance(), fake, log)
    check("block 1 saved, original ports switched off, in one fleet set", "CALL fleet set PORT_BLOCK=1 HONOR_ORIGINAL_PORTS=false" in calls(log), calls(log))
    log = os.path.join(tmp, "g2.log")
    st = drive(["f", ENTER] + [DOWN] * 10 + [ENTER, "y", ESC, "q"], instance(), fake, log)
    check("A (original 2456 ports) saved", "CALL fleet set HONOR_ORIGINAL_PORTS=true" in calls(log), calls(log))
    log = os.path.join(tmp, "g3.log")
    st = drive(["f", ENTER, DOWN, ENTER, "n", ESC, "q"], instance(), fake, log)
    check("declining the warning saves nothing", not any(c.startswith("CALL fleet set") for c in calls(log)), calls(log))
    log = os.path.join(tmp, "g4.log")
    # with the original ports already on, A is preselected: Enter on it changes nothing
    st = drive(["f", ENTER, ENTER, ESC, "q"], instance(fleet_extra="HONOR_ORIGINAL_PORTS=true\n"), fake, log)
    check("the current choice is preselected (Enter changes nothing)", not any(c.startswith("CALL fleet set") for c in calls(log)), calls(log))
    log = os.path.join(tmp, "g5.log")
    # switching away from A: from the preselected A, Up moves to block 9
    st = drive(["f", ENTER, UP, ENTER, "y", ESC, "q"], instance(fleet_extra="HONOR_ORIGINAL_PORTS=true\n"), fake, log)
    check("from A, choosing block 9 turns the original ports off", "CALL fleet set PORT_BLOCK=9 HONOR_ORIGINAL_PORTS=false" in calls(log), calls(log))

    print("- first-run setup in an empty directory")
    log = os.path.join(tmp, "h.log")
    d = instance(with_config=False)
    # y create; backend Docker Enter; name Enter (main); q. No password is asked: a password belongs to a world.
    keys = ["y", ENTER, ENTER, "q"]
    st = drive(keys, d, fake, log, wait=0.25)
    c = calls(log)
    check("init, backend and name were set", all(x in c for x in ["CALL init", "CALL fleet set BACKEND=docker", "CALL fleet set INSTANCE_ID=main"]), c)
    check("setup asked for no password", not any(x.startswith("CALL passwd") for x in c), c)

    print()
    print("ALL PASSED" if not failures else "FAILED: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
