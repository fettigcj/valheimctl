#!/usr/bin/env python3
# valheimctl web console: a small Flask app on top of the valheimctl command line.
#
# Copyright (C) 2026 Chris Fettig
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version. It is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License (the LICENSE file) for more details.
"""Every action goes through the valheimctl command line, exactly like the terminal menu, so the web console never has its own
idea of how to deploy a world. Passwords reach valheimctl on its standard input, never on a command line.

Run it with `valheimctl web run` (or `python3 web/app.py run` from the instance directory). Needs Flask 1.1 or newer
(Debian/Ubuntu: `apt install python3-flask`). The command line tool itself needs none of this."""
import argparse
import getpass
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_menu():
    """The menu's pure helpers (env parsing, raids/preset editing) are reused so both front ends write identical settings."""
    spec = importlib.util.spec_from_file_location("valheimctl_menu", os.path.join(HERE, "..", "tui", "menu.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


menu = _load_menu()

NN_RE = re.compile(r"^[1-9]$")
BACKUP_ID_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,200}$")
USER_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
ROLES = ("viewer", "admin")
MIN_PASSWORD = 5          # the game's own minimum for a join password
LOGIN_TRIES = 5
LOGIN_LOCK_SECONDS = 60
MAX_OUTPUT = 4000


# ---------------------------------------------------------------- settings, users, secrets (files under config/web)

def read_env(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return menu.parse_env_text(fh.read())
    except OSError:
        return {}


class Settings:
    """config/web.env: WEB_AUTH (both|admin|none), WEB_BIND, WEB_PORT, WEB_SECURE_COOKIE. Defaults are the safe ones."""

    def __init__(self, instance_dir):
        self.instance = instance_dir
        self.webdir = os.path.join(instance_dir, "config", "web")
        cfg = read_env(os.path.join(instance_dir, "config", "web.env"))
        fleet = read_env(os.path.join(instance_dir, "config", "fleet.env"))
        self.auth = cfg.get("WEB_AUTH", "both").strip().lower()
        self.bind = cfg.get("WEB_BIND", "127.0.0.1")
        self.secure_cookie = cfg.get("WEB_SECURE_COOKIE", "false").lower() == "true"
        block = int(fleet["PORT_BLOCK"]) if fleet.get("PORT_BLOCK", "").isdigit() else 0
        first = 2446 if fleet.get("HONOR_ORIGINAL_PORTS", "").lower() == "true" else 2000 + 100 * block
        self.port = int(cfg["WEB_PORT"]) if cfg.get("WEB_PORT", "").isdigit() else first   # the block's first port

    @property
    def flag_file(self):
        return os.path.join(self.webdir, "NO_AUTH_ON_PURPOSE.flag")

    def problem(self):
        """Why the console must not start, or None."""
        if self.auth not in ("both", "admin", "none"):
            return "WEB_AUTH must be both, admin or none (it is %r)" % self.auth
        if self.auth == "none" and not os.path.exists(self.flag_file):
            return ("WEB_AUTH=none means anyone who can reach the page can control every world. If that is what you want, create the empty "
                    "file %s to say so" % self.flag_file)
        return None


class Users:
    def __init__(self, webdir):
        self.path = os.path.join(webdir, "users.json")
        self.webdir = webdir

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def save(self, users):
        os.makedirs(self.webdir, exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(users, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def set(self, name, password, role):
        from werkzeug.security import generate_password_hash
        if not USER_RE.match(name):
            raise ValueError("a user name is 1 to 32 letters, digits, dot, dash or underscore")
        if role not in ROLES:
            raise ValueError("role must be viewer or admin")
        if len(password) < 8:
            raise ValueError("a console password must be at least 8 characters")
        users = self.load()
        users[name] = {"hash": generate_password_hash(password), "role": role}
        self.save(users)

    def remove(self, name):
        users = self.load()
        if name not in users:
            raise ValueError("no such user: %s" % name)
        del users[name]
        self.save(users)

    def check(self, name, password):
        from werkzeug.security import check_password_hash
        u = self.load().get(name)
        # Check a hash even for an unknown name so the response time does not reveal which names exist.
        digest = u["hash"] if u else "pbkdf2:sha256:1$x$0000000000000000000000000000000000000000000000000000000000000000"
        ok = check_password_hash(digest, password)
        return u["role"] if (u and ok) else None


def secret_key(webdir):
    path = os.path.join(webdir, "secret_key")
    try:
        with open(path, encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key
    except OSError:
        pass
    os.makedirs(webdir, exist_ok=True)
    key = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key + "\n")
    return key


# ---------------------------------------------------------------- talking to valheimctl

class Runner(menu.Runner):
    """The menu's runner, pinned to one instance directory and with a time limit (a first start downloads the game)."""

    def __init__(self, binpath, instance_dir, timeout=1800):
        super().__init__(binpath)
        self.instance = instance_dir
        self.timeout = timeout

    def run(self, args, stdin_text=None):
        env = dict(os.environ, VALHEIMCTL_INSTANCE_DIR=self.instance)
        try:
            p = subprocess.run([self.bin] + list(args), input=stdin_text, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               universal_newlines=True, cwd=self.instance, env=env, timeout=self.timeout)
            return p.returncode, p.stdout
        except subprocess.TimeoutExpired:
            return 124, "timed out after %d seconds; the command may still be running, check the world's state" % self.timeout
        except OSError as exc:
            return 127, "cannot run %s: %s" % (self.bin, exc)


def clean_output(text):
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text or "").strip()
    return text if len(text) <= MAX_OUTPUT else "...\n" + text[-MAX_OUTPUT:]


def generate_password():
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no look-alike characters
    return "".join(secrets.choice(alphabet) for _ in range(14))


# ---------------------------------------------------------------- the app

def create_app(instance_dir=None, runner=None):
    from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

    instance_dir = os.path.abspath(instance_dir or os.environ.get("VALHEIMCTL_INSTANCE_DIR") or os.getcwd())
    settings = Settings(instance_dir)
    users = Users(settings.webdir)
    if runner is None:
        runner = Runner(os.environ.get("VALHEIMCTL_BIN") or os.path.join(HERE, "..", "valheimctl"), instance_dir)

    app = Flask(__name__, template_folder=os.path.join(HERE, "templates"), static_folder=os.path.join(HERE, "static"))
    app.config.update(SECRET_KEY=secret_key(settings.webdir), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=settings.secure_cookie, MAX_CONTENT_LENGTH=64 * 1024)
    failures = {}   # (ip, name) -> [count, locked_until]

    # ---- who is this, and what may they do
    def current_role():
        if settings.auth == "none":
            return "admin"
        r = session.get("role")
        if r in ROLES and session.get("user") in users.load():
            return r
        return None

    @app.before_request
    def gate():
        g.role = current_role()
        if request.endpoint in ("login", "static"):
            return None
        if g.role is None and settings.auth != "admin":
            return redirect(url_for("login", next=request.path))
        if request.method == "POST":
            token = session.get("csrf")
            if not token or not secrets.compare_digest(token, request.form.get("csrf", "")):
                abort(400, "the form has expired; go back, reload the page and try again")
        return None

    @app.after_request
    def headers(resp):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
        return resp

    @app.context_processor
    def inject():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return {"role": getattr(g, "role", None), "csrf": session["csrf"], "user": session.get("user"), "auth_mode": settings.auth,
                "is_admin": getattr(g, "role", None) == "admin"}

    def need_admin():
        if g.role != "admin":
            if settings.auth == "admin" and g.role is None:
                return redirect(url_for("login", next=request.path))
            abort(403, "this needs an administrator login")
        return None

    def world_or_404(nn):
        if not NN_RE.match(nn):
            abort(404)
        return nn

    def report(rc, out, ok_text):
        out = clean_output(out)
        if rc == 0:
            flash(ok_text + ("\n" + out if out else ""), "ok")
        else:
            flash("That did not work (exit %d).\n%s" % (rc, out), "error")

    def worlds():
        rows, err = runner.json(["list"])
        return rows, err

    def world_config(nn):
        fleet = read_env(os.path.join(instance_dir, "config", "fleet.env"))
        own = read_env(os.path.join(instance_dir, "config", "worlds", "%s.env" % nn))
        return fleet, own

    def password_state(nn):
        own = os.path.exists(os.path.join(instance_dir, "config", "secrets", "%s.server.pass" % nn))
        shared = os.path.exists(os.path.join(instance_dir, "config", "secrets", "default.server.pass"))
        return own, shared

    # ---- login
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if settings.auth == "none":
            return redirect(url_for("index"))
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        nxt = request.values.get("next", "/")
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        if request.method == "POST":
            if not secrets.compare_digest(session["csrf"], request.form.get("csrf", "")):
                abort(400, "the form has expired; reload the page and try again")
            name = request.form.get("user", "")[:64]
            key = (request.remote_addr, name)
            count, until = failures.get(key, [0, 0])
            if until > time.time():
                flash("Too many attempts. Wait a minute and try again.", "error")
                return render_template("login.html", next=nxt), 429
            role = users.check(name, request.form.get("password", ""))
            if role:
                failures.pop(key, None)
                session.clear()
                session["user"], session["role"], session["csrf"] = name, role, secrets.token_hex(16)
                return redirect(nxt)
            count += 1
            failures[key] = [count, time.time() + LOGIN_LOCK_SECONDS if count >= LOGIN_TRIES else 0]
            flash("That user name or password is not right.", "error")
            return render_template("login.html", next=nxt), 401
        return render_template("login.html", next=nxt)

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ---- worlds
    @app.route("/")
    def index():
        rows, err = worlds()
        return render_template("worlds.html", rows=rows, error=err)

    @app.route("/world/<nn>")
    def world(nn, generated=None):
        nn = world_or_404(nn)
        rows, err = worlds()
        row = next((r for r in (rows or []) if r.get("world") == nn), None)
        if row is None:
            abort(404, err or "world %s is not managed here" % nn)
        fleet, own = world_config(nn)
        merged = dict(fleet, **own)
        preset, mods, _extra = menu.parse_server_args(merged.get("SERVER_ARGS", ""))
        own_pw, shared_pw = password_state(nn)
        return render_template("world.html", w=row, nn=nn, preset=preset, raids=mods.get("raids", ""), presets=menu.PRESETS,
                               raid_levels=menu.RAIDS, listed=merged.get("SERVER_PUBLIC", "true").lower() != "false",
                               own_pw=own_pw, shared_pw=shared_pw, generated=generated)

    @app.route("/world/<nn>/action/<act>", methods=["POST"])
    def action(nn, act):
        denied = need_admin()
        if denied:
            return denied
        nn = world_or_404(nn)
        table = {"start": (["start", nn], "Started."), "stop": (["stop", nn], "Stopped."),
                 "restart": (["restart", nn], "The game server was restarted."),
                 "apply": (["apply", nn, "--yes"], "Applied. The world was recreated with your saved settings.")}
        if act not in table:
            abort(404)
        args, ok = table[act]
        report(*runner.run(args if "--yes" in args else args + ["--yes"]), ok)
        return redirect(url_for("world", nn=nn))

    @app.route("/world/<nn>/settings", methods=["POST"])
    def settings_save(nn):
        denied = need_admin()
        if denied:
            return denied
        nn = world_or_404(nn)
        fleet, own = world_config(nn)
        cur = dict(fleet, **own).get("SERVER_ARGS", "")
        preset, raids = request.form.get("preset", ""), request.form.get("raids", "")
        if preset not in [v for _, v in menu.PRESETS] or raids not in [v for _, v in menu.RAIDS]:
            abort(400, "unknown preset or raids level")
        new = menu.with_raids(menu.with_preset(cur, preset), raids)
        listed = "true" if request.form.get("listed") == "yes" else "false"
        rc, out = runner.run(["set", nn, "SERVER_ARGS=" + new, "SERVER_PUBLIC=" + listed, "--no-apply"])
        report(rc, out, "Saved. It takes effect when you apply it (this restarts the world).")
        if rc == 0 and request.form.get("apply_now") == "yes":
            report(*runner.run(["apply", nn, "--yes"]), "Applied. The world was recreated with your saved settings.")
        return redirect(url_for("world", nn=nn))

    @app.route("/world/<nn>/password", methods=["POST"])
    def password(nn):
        denied = need_admin()
        if denied:
            return denied
        nn = world_or_404(nn)
        if request.form.get("mode") == "default":
            rc, out = runner.run(["passwd", nn, "server", "--use-default", "--yes"])
            report(rc, out, "This world now uses the shared default password.")
        else:
            generated = None
            if request.form.get("mode") == "generate":
                pw = generated = generate_password()
            else:
                pw = request.form.get("password", "")
                if pw != request.form.get("again", ""):
                    flash("The two passwords are not the same.", "error")
                    return redirect(url_for("world", nn=nn))
                if len(pw) < MIN_PASSWORD:
                    flash("A join password must be at least %d characters (a game rule)." % MIN_PASSWORD, "error")
                    return redirect(url_for("world", nn=nn))
            rc, out = runner.run(["passwd", nn, "server"], stdin_text=pw)
            report(rc, out, "Saved this world's own join password.")
            if rc != 0:
                return redirect(url_for("world", nn=nn))
            if request.form.get("apply_now") == "yes":
                report(*runner.run(["apply", nn, "--yes"]), "Applied. Players need the new password from now on.")
            else:
                flash("The new password is saved but not live yet: apply it (this restarts the world).", "ok")
            if generated:
                # Shown once, in this response only: never put it in the redirect, the flash cookie or a log.
                return world(nn, generated=generated)
        return redirect(url_for("world", nn=nn))

    # ---- backups
    @app.route("/world/<nn>/backups")
    def backups(nn):
        nn = world_or_404(nn)
        rows, err = runner.json(["backups", "list", nn])
        return render_template("backups.html", nn=nn, rows=rows, error=err)

    @app.route("/world/<nn>/restore", methods=["POST"])
    def restore(nn):
        denied = need_admin()
        if denied:
            return denied
        nn = world_or_404(nn)
        bid = request.form.get("id", "")
        if not BACKUP_ID_RE.match(bid):
            abort(400, "bad restore point")
        if request.form.get("confirm", "").strip().upper() != "RESTORE":
            flash("Nothing was changed: type RESTORE in the box to confirm.", "error")
            return redirect(url_for("backups", nn=nn))
        report(*runner.run(["restore", nn, bid, "--yes"]),
               "Restored. The previous state was snapshotted and parked, not deleted.")
        return redirect(url_for("world", nn=nn))

    return app


# ---------------------------------------------------------------- command line: run, and manage console accounts

def _read_password(prompt):
    if sys.stdin.isatty():
        a = getpass.getpass(prompt)
        if a != getpass.getpass("Again: "):
            sys.exit("the passwords do not match")
        return a
    return sys.stdin.readline().rstrip("\n")   # piped in: one line, never on a command line


def main(argv=None):
    ap = argparse.ArgumentParser(prog="valheimctl web", description="valheimctl web console")
    ap.add_argument("--instance", default=os.environ.get("VALHEIMCTL_INSTANCE_DIR") or os.getcwd(), help="instance directory (default: current)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="start the console")
    u = sub.add_parser("user", help="manage console accounts")
    usub = u.add_subparsers(dest="ucmd", required=True)
    a = usub.add_parser("add", help="add a user or change its password and role")
    a.add_argument("name")
    a.add_argument("--role", choices=ROLES, default="admin")
    usub.add_parser("list", help="list users")
    r = usub.add_parser("remove", help="remove a user")
    r.add_argument("name")
    args = ap.parse_args(argv)

    instance = os.path.abspath(args.instance)
    settings = Settings(instance)
    store = Users(settings.webdir)
    if args.cmd == "user":
        try:
            if args.ucmd == "add":
                store.set(args.name, _read_password("Password for %s: " % args.name), args.role)
                print("saved %s (%s)" % (args.name, args.role))
            elif args.ucmd == "remove":
                store.remove(args.name)
                print("removed %s" % args.name)
            else:
                for n, v in sorted(store.load().items()):
                    print("%-20s %s" % (n, v["role"]))
        except ValueError as exc:
            sys.exit(str(exc))
        return 0
    bad = settings.problem()
    if bad:
        sys.exit(bad)
    if settings.auth != "none" and not store.load():
        sys.exit("there are no console users yet. Create one:  valheimctl web user add <name>")
    try:
        app = create_app(instance)
    except ImportError:
        sys.exit("the web console needs Flask (Debian/Ubuntu: apt install python3-flask; or: python3 -m pip install flask)")
    print("valheimctl web console for %s on http://%s:%d/  (login: %s)" % (instance, settings.bind, settings.port, settings.auth), flush=True)
    app.run(host=settings.bind, port=settings.port, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
