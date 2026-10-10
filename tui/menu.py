#!/usr/bin/env python3
# valheimctl menu: a terminal menu for valheimctl (arrow keys), built on Python's own curses module, so no libraries to install.
#
# Copyright (C) 2026 Chris Fettig
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version. It is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License (the LICENSE file) for more details.
"""Every action goes through the valheimctl command line (VALHEIMCTL_BIN), so the menu never has its own idea of how to
deploy a world. Started with `valheimctl menu`. Written for Python 3.8 and newer."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------- pure logic (unit-tested without a terminal)

PRESETS = [("Game default", ""), ("Casual", "casual"), ("Easy", "easy"), ("Normal", "normal"), ("Hard", "hard"),
           ("Hardcore", "hardcore"), ("Immersive", "immersive"), ("Hammer", "hammer")]
RAIDS = [("Game default", ""), ("None", "none"), ("Much less", "muchless"), ("Less", "less"), ("More", "more"),
         ("Much more", "muchmore")]
YES_NO = [("Yes", "true"), ("No", "false")]
SUFFIX_RE = re.compile(r"^[A-Za-z0-9_-]+$")
INSTANCE_RE = re.compile(r"^[a-z0-9-]{1,16}$")


def parse_env_text(text):
    """KEY=value lines (valheimctl's file format) -> dict. Comments and blank lines are skipped."""
    out = {}
    for line in text.splitlines():
        line = line.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if not m:
            continue
        val = m.group(2)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[m.group(1)] = val
    return out


def read_env_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return parse_env_text(fh.read())
    except OSError:
        return {}


def parse_server_args(s):
    """'-preset hard -modifier raids none -foo' -> (preset, {modifier: level}, [other tokens])."""
    toks = (s or "").split()
    preset, mods, rest, i = "", {}, [], 0
    while i < len(toks):
        t = toks[i]
        if t == "-preset" and i + 1 < len(toks):
            preset = toks[i + 1]
            i += 2
        elif t == "-modifier" and i + 2 < len(toks):
            mods[toks[i + 1]] = toks[i + 2]
            i += 3
        else:
            rest.append(t)
            i += 1
    return preset, mods, rest


def build_server_args(preset, mods, rest):
    """Canonical order, so a preset can never overwrite a modifier: preset, then modifiers, then everything else."""
    parts = []
    if preset:
        parts += ["-preset", preset]
    for name, level in mods.items():
        parts += ["-modifier", name, level]
    return " ".join(parts + list(rest))


def with_raids(args, level):
    preset, mods, rest = parse_server_args(args)
    if level:
        mods["raids"] = level
    else:
        mods.pop("raids", None)
    return build_server_args(preset, mods, rest)


def with_preset(args, preset_value):
    _, mods, rest = parse_server_args(args)
    return build_server_args(preset_value, mods, rest)


def free_world_numbers(used):
    return [n for n in range(1, 10) if n not in set(used)]


def world_ports(n, block=0, honor=False):
    """The game and query UDP ports of world n (mirrors docs/ports.md)."""
    base = 2446 if honor else 2000 + 100 * int(block)
    game = base + 10 * int(n)
    return game, game + 1


def choice_label(options, value):
    for label, val in options:
        if val == value:
            return label
    return value or "Game default"


def local_time(utc_text):
    """'2026-10-09 11:29:15' (UTC) -> local 'YYYY-MM-DD HH:MM'."""
    try:
        dt = datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return utc_text


def parse_world_number(name):
    m = re.match(r"^(0[1-9])\.env$", name)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- talking to valheimctl

class Runner:
    def __init__(self, binpath):
        self.bin = binpath

    def run(self, args, stdin_text=None):
        """-> (exit code, combined output). A password goes through stdin, never through the command line."""
        try:
            p = subprocess.run([self.bin] + list(args), input=stdin_text, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               universal_newlines=True)
            return p.returncode, p.stdout
        except OSError as exc:
            return 127, "cannot run %s: %s" % (self.bin, exc)

    def stream(self, args, on_line, stdin_text=None):
        """Run and call on_line(text) for each output line as it arrives -> exit code."""
        try:
            p = subprocess.Popen([self.bin] + list(args), stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        except OSError as exc:
            on_line("cannot run %s: %s" % (self.bin, exc))
            return 127
        if stdin_text is not None:
            p.stdin.write(stdin_text)
            p.stdin.close()
        for line in p.stdout:
            on_line(line.rstrip("\n"))
        return p.wait()

    def json(self, args):
        rc, out = self.run(list(args) + ["--json"])
        if rc != 0:
            return None, out
        try:
            return json.loads(out[out.index("["):]), ""
        except (ValueError, json.JSONDecodeError):
            return None, out


# ---------------------------------------------------------------- the screens

HELP_MAIN = "Up/Down choose   Enter open   A add world   D remove world   F instance settings   R refresh   Q quit"


class App:
    def __init__(self, stdscr, curses_mod, runner, inst_dir):
        self.c = curses_mod
        self.s = stdscr
        self.run = runner
        self.dir = inst_dir
        self.cfg = os.path.join(inst_dir, "config")
        self.pending = set()          # worlds with saved-but-not-applied changes (this session)
        self.notice = ""
        self.c.curs_set(0)
        self.s.keypad(True)
        try:
            self.c.use_default_colors()
            self.c.start_color()
            self.c.init_pair(1, self.c.COLOR_CYAN, -1)     # headings
            self.c.init_pair(2, self.c.COLOR_GREEN, -1)    # ok
            self.c.init_pair(3, self.c.COLOR_RED, -1)      # problems
            self.c.init_pair(4, self.c.COLOR_YELLOW, -1)   # notices
        except self.c.error:
            pass

    # ---- config access
    def fleet(self):
        return read_env_file(os.path.join(self.cfg, "fleet.env"))

    def world_cfg(self, n):
        own = read_env_file(os.path.join(self.cfg, "worlds", "%02d.env" % n))
        merged = dict(self.fleet())
        merged.update(own)
        return merged, own

    def has_instance(self):
        return os.path.isfile(os.path.join(self.cfg, "fleet.env"))

    # ---- drawing primitives
    def attr(self, pair):
        try:
            return self.c.color_pair(pair)
        except self.c.error:
            return 0

    def put(self, y, x, text, attr=0):
        h, w = self.s.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        try:
            self.s.addnstr(y, x, text, max(0, w - x - 1), attr)
        except self.c.error:
            pass

    def frame(self, title, footer):
        self.s.erase()
        h, w = self.s.getmaxyx()
        self.put(0, 0, (" " + title).ljust(w - 1), self.c.A_REVERSE | self.c.A_BOLD)
        self.put(h - 1, 0, (" " + footer).ljust(w - 1), self.c.A_REVERSE)
        if self.notice:
            self.put(h - 2, 1, self.notice, self.attr(4) | self.c.A_BOLD)

    def key(self):
        """One key press as a token: UP DOWN LEFT RIGHT ENTER ESC BACKSPACE PGUP PGDN HOME END RESIZE, or the character."""
        try:
            k = self.s.get_wch()
        except self.c.error:
            return "RESIZE"
        if isinstance(k, str):
            if k in ("\n", "\r"):
                return "ENTER"
            if k == "\x1b":
                return "ESC"
            if k in ("\x7f", "\b"):
                return "BACKSPACE"
            return k
        table = {self.c.KEY_UP: "UP", self.c.KEY_DOWN: "DOWN", self.c.KEY_LEFT: "LEFT", self.c.KEY_RIGHT: "RIGHT",
                 self.c.KEY_ENTER: "ENTER", self.c.KEY_BACKSPACE: "BACKSPACE", self.c.KEY_NPAGE: "PGDN",
                 self.c.KEY_PPAGE: "PGUP", self.c.KEY_HOME: "HOME", self.c.KEY_END: "END", self.c.KEY_RESIZE: "RESIZE",
                 self.c.KEY_DC: "DELETE"}
        return table.get(k, "")

    # ---- generic list menu
    def menu(self, title_fn, items_fn, footer, on_key=None):
        """items_fn() -> list of dicts: kind header|blank|line|item, label, value, do. Runs until an item's `do` returns 'back'."""
        sel = 0
        top = 0
        while True:
            items = items_fn()
            selectable = [i for i, it in enumerate(items) if it["kind"] == "item"]
            if not selectable:
                selectable = [0]
            if sel not in selectable:
                sel = min(selectable, key=lambda i: abs(i - sel))
            self.frame(title_fn(), footer)
            h, w = self.s.getmaxyx()
            body = h - 4
            if sel < top:
                top = sel
            if sel >= top + body:
                top = sel - body + 1
            for row, idx in enumerate(range(top, min(len(items), top + body))):
                it = items[idx]
                y = 2 + row
                if it["kind"] == "header":
                    self.put(y, 1, it["label"], self.attr(1) | self.c.A_BOLD)
                elif it["kind"] == "line":
                    self.put(y, 2, it["label"], it.get("attr", 0))
                elif it["kind"] == "item":
                    text = "  " + it["label"].ljust(30) + (" " + str(it.get("value", "")) if it.get("value", "") != "" else "")
                    self.put(y, 0, text.ljust(w - 1), self.c.A_REVERSE if idx == sel else 0)
            self.s.refresh()
            k = self.key()
            if k == "RESIZE":
                continue
            if on_key:
                r = on_key(k, items, sel)
                if r == "back":
                    return
                if r == "handled":
                    continue
            if k in ("UP", "k"):
                pos = selectable.index(sel)
                sel = selectable[max(0, pos - 1)]
            elif k in ("DOWN", "j"):
                pos = selectable.index(sel)
                sel = selectable[min(len(selectable) - 1, pos + 1)]
            elif k == "HOME":
                sel = selectable[0]
            elif k == "END":
                sel = selectable[-1]
            elif k == "PGDN":
                pos = selectable.index(sel)
                sel = selectable[min(len(selectable) - 1, pos + max(1, body - 2))]
            elif k == "PGUP":
                pos = selectable.index(sel)
                sel = selectable[max(0, pos - max(1, body - 2))]
            elif k == "ENTER":
                it = items[sel] if sel < len(items) else None
                if it and it["kind"] == "item" and it.get("do"):
                    self.notice = ""
                    if it["do"]() == "back":
                        return
            elif k in ("ESC", "LEFT", "q") and on_key is None:
                return

    # ---- dialogs
    def box(self, title, lines, footer="", input_text=None, input_label=""):
        h, w = self.s.getmaxyx()
        width = min(w - 4, max([len(l) for l in lines] + [len(title) + 4, len(footer) + 4, 40]) + 4)
        height = len(lines) + 4 + (2 if input_text is not None else 0)
        y0, x0 = max(1, (h - height) // 2), max(1, (w - width) // 2)
        for r in range(height):
            self.put(y0 + r, x0, " " * width, self.c.A_REVERSE if r == 0 else 0)
        self.put(y0, x0, (" " + title).ljust(width), self.c.A_REVERSE | self.c.A_BOLD)
        for i, line in enumerate(lines):
            self.put(y0 + 2 + i, x0 + 2, line[: width - 4])
        row = y0 + 2 + len(lines)
        if input_text is not None:
            self.put(row + 1, x0 + 2, (input_label + input_text)[-(width - 4):])
        self.put(y0 + height - 1, x0 + 2, footer[: width - 4], self.attr(1))
        return y0, x0, width, row + 1

    def message(self, title, lines, bad=False):
        self.frame("valheimctl menu", "Press any key")
        self.box(title, lines, "Press any key to continue")
        self.s.refresh()
        self.key()

    def confirm(self, title, lines):
        while True:
            self.frame("valheimctl menu", "Y yes   N no")
            self.box(title, lines + ["", "Y = yes, N = no"], "Y yes   N / Esc no")
            self.s.refresh()
            k = self.key()
            if k in ("y", "Y"):
                return True
            if k in ("n", "N", "ESC", "ENTER"):
                return False

    def choose(self, title, options, current_value=None, note=None):
        """options: [(label, value)] -> chosen value, or None if cancelled."""
        sel = 0
        for i, (_, v) in enumerate(options):
            if v == current_value:
                sel = i
        while True:
            self.frame("valheimctl menu", "Up/Down choose   Enter select   Esc cancel")
            lines = ([note, ""] if note else []) + [("> " if i == sel else "  ") + lab for i, (lab, _) in enumerate(options)]
            self.box(title, lines, "Up/Down choose   Enter select   Esc cancel")
            self.s.refresh()
            k = self.key()
            if k in ("UP", "k"):
                sel = max(0, sel - 1)
            elif k in ("DOWN", "j"):
                sel = min(len(options) - 1, sel + 1)
            elif k == "ENTER":
                return options[sel][1]
            elif k == "ESC":
                return None

    def ask(self, title, prompt, initial="", secret=False, validate=None, hint=()):
        buf = list(initial)
        pos = len(buf)
        err = ""
        while True:
            shown = ("*" * len(buf)) if secret else "".join(buf)
            self.frame("valheimctl menu", "Enter accept   Esc cancel")
            lines = [prompt] + list(hint) + ([""] + [err] if err else [])
            y0, x0, width, row = self.box(title, lines, "Enter accept   Esc cancel", input_text=shown + "_", input_label="> ")
            self.s.refresh()
            k = self.key()
            if k == "ESC":
                return None
            if k == "ENTER":
                value = "".join(buf)
                msg = validate(value) if validate else ""
                if msg:
                    err = msg
                    continue
                return value
            err = ""
            if k == "BACKSPACE" and pos > 0:
                del buf[pos - 1]
                pos -= 1
            elif k == "DELETE" and pos < len(buf):
                del buf[pos]
            elif k == "LEFT":
                pos = max(0, pos - 1)
            elif k == "RIGHT":
                pos = min(len(buf), pos + 1)
            elif k == "HOME":
                pos = 0
            elif k == "END":
                pos = len(buf)
            elif len(k) == 1 and k.isprintable():
                buf.insert(pos, k)
                pos += 1

    def ask_password(self, who):
        while True:
            p1 = self.ask("Join password", "Password players type to join %s (at least 5 characters):" % who, secret=True,
                          validate=lambda v: "" if len(v) >= 5 else "At least 5 characters (a game rule).")
            if p1 is None:
                return None
            p2 = self.ask("Join password", "Type it again to confirm:", secret=True)
            if p2 is None:
                return None
            if p1 == p2:
                return p1
            self.message("Join password", ["The two passwords did not match. Try again."])

    def logged(self, title, args, stdin_text=None):
        """Run a valheimctl command and show its output as it arrives."""
        lines = []
        h, w = self.s.getmaxyx()

        def on_line(text):
            lines.append(text)
            self.frame(title, "Working... (the first start of a world downloads the game: this can take several minutes)")
            body = h - 5
            for i, l in enumerate(lines[-body:]):
                self.put(2 + i, 1, l)
            self.s.refresh()

        self.frame(title, "Working...")
        self.put(2, 1, "Starting...")
        self.s.refresh()
        rc = self.run.stream(args, on_line, stdin_text)
        self.frame(title, "Press any key")
        body = h - 6
        for i, l in enumerate(lines[-body:]):
            self.put(2 + i, 1, l)
        self.put(h - 3, 1, "Finished." if rc == 0 else "FAILED (exit %d). Read the lines above." % rc,
                 self.attr(2 if rc == 0 else 3) | self.c.A_BOLD)
        self.s.refresh()
        self.key()
        return rc

    # ---- setup (no instance in this directory yet)
    def setup(self):
        here = self.dir
        self.frame("valheimctl menu - first setup", "Enter continue   Esc quit")
        if not self.confirm("No instance here", [
                "There is no valheimctl instance in:", "  " + here, "",
                "An instance is just this directory: it will hold config/, worlds/ and backups/.",
                "Create it here?"]):
            return False
        backend = self.choose("Where do the worlds run?", [("Docker (this machine)", "docker"), ("Podman (this machine)", "podman"),
                                                          ("Kubernetes (a cluster)", "k8s")], "docker")
        if backend is None:
            return False
        name = self.ask("Instance name", "A short name for this instance (lowercase letters, digits, hyphen):", "main",
                        validate=lambda v: "" if INSTANCE_RE.match(v) else "Use 1-16 characters: a-z, 0-9, hyphen.")
        if name is None:
            return False
        extra = []
        if backend == "k8s":
            ns = self.ask("Kubernetes namespace", "Namespace the worlds live in (it must already exist):", "valheim")
            if ns is None:
                return False
            kc = self.ask("Kubernetes credentials", "Path of the kubeconfig file to use (leave empty for kubectl's default):", "")
            if kc is None:
                return False
            extra = [["fleet", "set", "K8S_NAMESPACE=" + ns]] + ([["fleet", "set", "K8S_KUBECONFIG=" + kc]] if kc else [])
        pw = self.ask_password("your worlds")
        if pw is None:
            return False
        steps = [(["init"], None), (["fleet", "set", "BACKEND=" + backend], None), (["fleet", "set", "INSTANCE_ID=" + name], None)]
        steps += [(e, None) for e in extra] + [(["passwd", "default", "server"], pw + "\n")]
        for args, stdin_text in steps:
            rc, out = self.run.run(args, stdin_text)
            if rc != 0:
                self.message("Setup stopped", ["valheimctl " + " ".join(args[:2]) + " failed:"] + out.strip().splitlines()[-6:])
                return False
        self.notice = "Instance created. Add your first world with A."
        return True

    # ---- main screen: the worlds
    def main_screen(self):
        data = {"rows": [], "err": ""}

        def refresh():
            self.frame("valheimctl menu", "Reading worlds...")
            self.put(2, 2, "Reading the state of your worlds...")
            self.s.refresh()
            rows, err = self.run.json(["list"])
            data["rows"], data["err"] = (rows or []), err

        refresh()

        def title():
            f = self.fleet()
            return "valheimctl menu   instance %s   backend %s" % (f.get("INSTANCE_ID", "main"), f.get("BACKEND", "docker"))

        def items():
            its = []
            if data["err"]:
                its.append({"kind": "line", "label": "Could not read the worlds:", "attr": self.attr(3)})
                for l in data["err"].strip().splitlines()[-4:]:
                    its.append({"kind": "line", "label": l})
                its.append({"kind": "blank"})
            its.append({"kind": "header", "label": "  World  Name                          State        Players  Game port (UDP)"})
            for r in data["rows"]:
                n = int(r["world"])
                port = r.get("game_port", "")
                label = "%s    %s %s %s %s" % (r["world"], r["name"][:28].ljust(28), str(r["state"])[:12].ljust(12),
                                              str(r.get("players", "-")).ljust(7), port)
                its.append({"kind": "item", "label": label, "value": "*" if n in self.pending else "", "do": (lambda n=n: self.world_screen(n, refresh))})
            if not data["rows"]:
                its.append({"kind": "line", "label": "No worlds yet. Press A to add one."})
            its.append({"kind": "blank"})
            its.append({"kind": "line", "label": "A = add a world   D = remove the highlighted world   F = settings shared by every world"})
            return its

        def on_key(k, its, sel):
            rows = data["rows"]
            cur = None
            if sel < len(its) and its[sel]["kind"] == "item":
                cur = int(its[sel]["label"][:2])
            if k in ("q", "Q", "ESC"):
                return "back"
            if k in ("r", "R"):
                refresh()
                return "handled"
            if k in ("a", "A"):
                self.add_world([int(r["world"]) for r in rows])
                refresh()
                return "handled"
            if k in ("d", "D") and cur:
                self.remove_world(cur)
                refresh()
                return "handled"
            if k in ("f", "F"):
                self.fleet_screen()
                refresh()
                return "handled"
            return None

        self.menu(title, items, HELP_MAIN, on_key)

    # ---- add / remove
    def add_world(self, used):
        free = free_world_numbers(used)
        if not free:
            self.message("Add a world", ["This instance already has nine worlds (the most one instance holds)."])
            return
        f = self.fleet()
        if not (os.path.isfile(os.path.join(self.cfg, "secrets", "default.server.pass"))):
            if not self.confirm("Join password", ["No join password is set yet.", "Set one now?"]):
                return
            pw = self.ask_password("your worlds")
            if pw is None:
                return
            rc, out = self.run.run(["passwd", "default", "server"], pw + "\n")
            if rc != 0:
                self.message("Join password", out.strip().splitlines()[-5:])
                return
        n = self.choose("Add a world: which slot?", [("World %d   UDP %d-%d" % (x, *world_ports(x, f.get("PORT_BLOCK", "0"), f.get("HONOR_ORIGINAL_PORTS") == "true")), x)
                                                      for x in free], free[0], note="Each slot has its own ports.")
        if n is None:
            return
        name = self.ask("Add a world", "Name for the world (letters, digits, _ and -; no spaces):", "",
                        validate=lambda v: "" if SUFFIX_RE.match(v) else "Use letters, digits, underscore or hyphen only.")
        if not name:
            return
        g, q = world_ports(n, f.get("PORT_BLOCK", "0"), f.get("HONOR_ORIGINAL_PORTS") == "true")
        if not self.confirm("Create this world?", ["Slot %d, named valheim%02d-%s" % (n, n, name),
                                                   "Players join on UDP port %d (and %d)." % (g, q),
                                                   "It starts now; the first start downloads the game (several minutes)."]):
            return
        self.logged("Creating world %d" % n, ["new", str(n), name, "-y"])

    def remove_world(self, n):
        if not self.confirm("Remove world %d?" % n, [
                "This stops the world and stops managing it.",
                "Its world data, backups and settings file are NOT deleted:",
                "the settings are kept as config/worlds/%02d.env.removed-..." % n,
                "(you can rename that file back to manage the world again)."]):
            return
        self.logged("Removing world %d" % n, ["remove", str(n), "-y"])
        self.pending.discard(n)

    # ---- one world
    def world_screen(self, n, refresh_main):
        def title():
            return "World %02d" % n

        def save(key, value):
            rc, out = self.run.run(["set", str(n), "%s=%s" % (key, value), "--no-apply"])
            if rc != 0:
                self.message("Could not save", out.strip().splitlines()[-6:])
                return False
            self.pending.add(n)
            self.notice = "Saved. Choose 'Apply saved changes' to make it live (the world restarts)."
            return True

        def edit_choice(key, label, options, transform=None):
            def do():
                merged, _ = self.world_cfg(n)
                cur = merged.get(key, "")
                if transform:
                    cur = transform[0](cur)
                v = self.choose(label, options, cur)
                if v is None:
                    return None
                new = transform[1](merged.get(key, ""), v) if transform else v
                save(key, new)
            return do

        def edit_text(key, label, prompt, hint=()):
            def do():
                merged, _ = self.world_cfg(n)
                v = self.ask(label, prompt, merged.get(key, ""), hint=hint)
                if v is not None:
                    save(key, v)
            return do

        st = {"row": {}}

        def load():
            rows, _ = self.run.json(["list"])
            st["row"] = next((r for r in (rows or []) if int(r["world"]) == n), {})

        def action(args, title_, confirm_lines=None):
            def do():
                if confirm_lines and not self.confirm(title_, confirm_lines):
                    return None
                self.logged(title_, args)
                load()
            return do

        def apply_now():
            self.logged("Applying changes to world %d" % n, ["apply", str(n), "-y"])
            self.pending.discard(n)
            load()

        def items():
            merged, own = self.world_cfg(n)
            row = st["row"]
            preset, mods, rest = parse_server_args(merged.get("SERVER_ARGS", ""))
            running = str(row.get("state", "")) in ("running",) or str(row.get("state", "")).startswith("ready 1")
            its = [{"kind": "header", "label": "  %s" % row.get("name", "world %d" % n)},
                   {"kind": "line", "label": "State: %s   Players: %s   Game port: UDP %s" % (row.get("state", "?"), row.get("players", "-"), row.get("game_port", "?"))}]
            if n in self.pending:
                its.append({"kind": "line", "label": "* There are saved changes that are not applied yet.", "attr": self.attr(4) | self.c.A_BOLD})
            its += [{"kind": "blank"}, {"kind": "header", "label": "  Settings (Enter changes one)"},
                    {"kind": "item", "label": "Raids", "value": choice_label(RAIDS, mods.get("raids", "")),
                     "do": edit_choice("SERVER_ARGS", "Raids", RAIDS, (lambda cur: parse_server_args(cur)[1].get("raids", ""), with_raids))},
                    {"kind": "item", "label": "Difficulty preset", "value": choice_label(PRESETS, preset),
                     "do": edit_choice("SERVER_ARGS", "Difficulty preset", PRESETS, (lambda cur: parse_server_args(cur)[0], with_preset))},
                    {"kind": "item", "label": "Listed in the server list", "value": "Yes" if merged.get("SERVER_PUBLIC", "true") == "true" else "No",
                     "do": edit_choice("SERVER_PUBLIC", "Listed in the server list?", YES_NO)},
                    {"kind": "item", "label": "Name shown to players", "value": merged.get("SERVER_NAME", "(world name)"),
                     "do": edit_text("SERVER_NAME", "Name shown to players", "Name players see in the server list:")},
                    {"kind": "item", "label": "Admins (Steam IDs)", "value": merged.get("ADMINLIST_IDS", "(none)")[:40],
                     "do": edit_text("ADMINLIST_IDS", "Admins", "Steam IDs of admins, separated by spaces:",
                                     ("Find an ID at steamid.io.",))},
                    {"kind": "item", "label": "Extra game arguments", "value": " ".join(rest) or "(none)",
                     "do": edit_text("SERVER_ARGS", "Game arguments (advanced)", "Full list of game arguments:",
                                     ("Edit with care: Raids and Difficulty above write here too.",))},
                    {"kind": "blank"}, {"kind": "header", "label": "  Actions"},
                    {"kind": "item", "label": "Apply saved changes (restarts the world)", "do": apply_now},
                    {"kind": "item", "label": "Stop the world" if running else "Start the world",
                     "do": action(["stop", str(n), "-y"] if running else ["start", str(n)], "Stop world %d?" % n if running else "Start world %d" % n,
                                  ["Players are disconnected after the world saves."] if running else None)},
                    {"kind": "item", "label": "Restart the game only", "do": action(["service", str(n), "valheim-server", "restart", "-y"],
                                                                                   "Restart world %d" % n, ["The game restarts; players are disconnected."])},
                    {"kind": "item", "label": "Backups and restore...", "do": lambda: self.backups_screen(n)},
                    {"kind": "item", "label": "Back", "do": lambda: "back"}]
            return its

        self.frame("World %02d" % n, "Reading the world...")
        self.put(2, 2, "Reading the state of the world...")
        self.s.refresh()
        load()
        self.menu(title, items, "Up/Down choose   Enter select   Esc back", None)
        refresh_main()

    # ---- backups
    def backups_screen(self, n):
        st = {"rows": None, "err": ""}

        def load():
            st["rows"], st["err"] = self.run.json(["backups", "list", str(n)])

        def backup_now():
            self.logged("Backup of world %d" % n, ["backup", str(n)])
            load()

        def restore(r):
            self.restore_dialog(n, r)
            load()

        def items():
            rows, err = st["rows"], st["err"]
            its = [{"kind": "header", "label": "  Restore points for world %d (newest first). Enter on one to restore it." % n}]
            if rows is None:
                its.append({"kind": "line", "label": "Could not list backups:", "attr": self.attr(3)})
                its += [{"kind": "line", "label": l} for l in err.strip().splitlines()[-4:]]
            for r in rows or []:
                label = "%-22s %-10s %s  save %s" % (r["id"], r["source"], local_time(r["created_utc"]), r.get("save", "?"))
                its.append({"kind": "item", "label": label, "do": (lambda r=r: restore(r))})
            its += [{"kind": "blank"}, {"kind": "item", "label": "Take a backup now", "do": backup_now},
                    {"kind": "item", "label": "Back", "do": lambda: "back"}]
            return its

        self.frame("Backups", "Reading backups...")
        self.put(2, 2, "Listing restore points...")
        self.s.refresh()
        load()
        self.menu(lambda: "Backups - world %02d" % n, items, "Up/Down choose   Enter select   Esc back")

    def restore_dialog(self, n, r):
        if not self.confirm("Restore world %d?" % n, [
                "Restore point: %s  (%s, %s)" % (r["id"], r["source"], local_time(r["created_utc"])),
                "",
                "The world is stopped, the current world is saved as a snapshot",
                "and parked (never deleted), the restore point is copied in,",
                "the world starts, and the menu checks the right save loaded.",
                "Anything played since then is not in the restored world."]):
            return
        self.logged("Restoring world %d" % n, ["restore", str(n), r["id"], "-y"])

    # ---- settings shared by every world
    def fleet_screen(self):
        def save(key, value):
            rc, out = self.run.run(["fleet", "set", "%s=%s" % (key, value)])
            if rc != 0:
                self.message("Could not save", out.strip().splitlines()[-6:])
            else:
                self.notice = "Saved. Running worlds pick this up the next time they are applied."

        def choice(key, label, options, default=""):
            def do():
                v = self.choose(label, options, self.fleet().get(key, default))
                if v is not None:
                    save(key, v)
            return do

        def text(key, label, prompt, hint=()):
            def do():
                v = self.ask(label, prompt, self.fleet().get(key, ""), hint=hint)
                if v is not None:
                    save(key, v)
            return do

        def password():
            pw = self.ask_password("your worlds")
            if pw is not None:
                rc, out = self.run.run(["passwd", "default", "server"], pw + "\n")
                self.message("Join password", ["Saved. It applies to each world the next time it is applied."] if rc == 0 else out.strip().splitlines()[-5:])

        def items():
            f = self.fleet()
            return [
                {"kind": "header", "label": "  Settings shared by every world (a world's own setting wins)"},
                {"kind": "item", "label": "Port block", "value": "%s  (UDP %d-%d ...)" % (f.get("PORT_BLOCK", "0"), world_ports(1, f.get("PORT_BLOCK", "0"), f.get("HONOR_ORIGINAL_PORTS") == "true")[0],
                                                                                      world_ports(1, f.get("PORT_BLOCK", "0"), f.get("HONOR_ORIGINAL_PORTS") == "true")[1]),
                 "do": choice("PORT_BLOCK", "Port block (changes every world's ports)", [("%d  (ports %d00s)" % (i, 20 + i), str(i)) for i in range(10)], "0")},
                {"kind": "item", "label": "Use the original ports (2456...)", "value": "Yes" if f.get("HONOR_ORIGINAL_PORTS") == "true" else "No",
                 "do": choice("HONOR_ORIGINAL_PORTS", "Use the original ports?", YES_NO, "false")},
                {"kind": "item", "label": "Address players use", "value": f.get("PUBLIC_HOST", "(not set)"),
                 "do": text("PUBLIC_HOST", "Address players use", "Host name or IP shown as the join address:")},
                {"kind": "item", "label": "Listed in the server list", "value": "Yes" if f.get("SERVER_PUBLIC", "true") == "true" else "No",
                 "do": choice("SERVER_PUBLIC", "Worlds appear in the server list?", YES_NO, "true")},
                {"kind": "item", "label": "Admins (Steam IDs)", "value": f.get("ADMINLIST_IDS", "(none)")[:40],
                 "do": text("ADMINLIST_IDS", "Admins", "Steam IDs of admins, separated by spaces:")},
                {"kind": "item", "label": "Update-check hours (UTC)", "value": f.get("UPDATE_HOURS", "0,6,12,18"),
                 "do": text("UPDATE_HOURS", "Update-check hours", "Hours (0-23, UTC) separated by commas:", ("Each world checks at a staggered minute.",))},
                {"kind": "item", "label": "Change the join password...", "do": password},
                {"kind": "blank"},
                {"kind": "line", "label": "Instance: %s     Backend: %s     Folder: %s" % (f.get("INSTANCE_ID", "main"), f.get("BACKEND", "docker"), self.dir)},
                {"kind": "item", "label": "Back", "do": lambda: "back"}]

        self.menu(lambda: "Settings shared by every world", items, "Up/Down choose   Enter select   Esc back")


def main():
    binpath = os.environ.get("VALHEIMCTL_BIN")
    inst = os.environ.get("VALHEIMCTL_INSTANCE_DIR", os.getcwd())
    if not binpath:
        print("Run this through: valheimctl menu", file=sys.stderr)
        return 2
    os.environ.setdefault("ESCDELAY", "25")
    import curses

    def run(stdscr):
        app = App(stdscr, curses, Runner(binpath), inst)
        if not app.has_instance() and not app.setup():
            return
        app.main_screen()

    curses.wrapper(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
