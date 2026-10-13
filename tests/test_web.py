#!/usr/bin/env python3
# Copyright (C) 2026 Chris Fettig
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the web console with a fake valheimctl (no engine, no network). Needs Flask. Run: python3 tests/test_web.py"""
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    import flask  # noqa: F401
except ImportError:
    print("SKIP: Flask is not installed (apt install python3-flask)")
    sys.exit(0)

spec = importlib.util.spec_from_file_location("webapp", os.path.join(HERE, "..", "web", "app.py"))
webapp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webapp)

ROWS = [{"world": "1", "name": "valheim01-Test", "game_port": "2110", "state": "running", "players": "0", "memory": "1.7GiB"}]
BACKUPS = [{"id": "snap-1", "source": "snapshot", "created_utc": "2026-10-12T10:00:00Z", "save": "12", "size_kb": "900", "vs_last_restore": ""}]


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.fail = None   # substring of an argument that makes the call fail

    def run(self, args, stdin_text=None):
        self.calls.append((list(args), stdin_text))
        if self.fail and self.fail in args:
            return 1, "refused: 2 player(s) connected"
        return 0, "ok"

    def json(self, args):   # read-only listings are not recorded: tests look at the actions
        if args[0] == "list":
            return ROWS, ""
        if args[0] == "backups":
            return BACKUPS, ""
        return None, "unknown"


class Base(unittest.TestCase):
    auth = "both"

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "config", "worlds"))
        os.makedirs(os.path.join(self.dir, "config", "secrets"))
        with open(os.path.join(self.dir, "config", "fleet.env"), "w") as fh:
            fh.write("PORT_BLOCK=1\nSERVER_ARGS=-preset hard\n")
        with open(os.path.join(self.dir, "config", "worlds", "01.env"), "w") as fh:
            fh.write("SUFFIX=Test\n")
        with open(os.path.join(self.dir, "config", "web.env"), "w") as fh:
            fh.write("WEB_AUTH=%s\n" % self.auth)
        u = webapp.Users(os.path.join(self.dir, "config", "web"))
        u.set("boss", "correct horse", "admin")
        u.set("kid", "another phrase", "viewer")
        self.runner = FakeRunner()
        self.app = webapp.create_app(self.dir, self.runner)
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def csrf(self, path="/login"):
        r = self.c.get(path)
        return re.search(r'name="csrf" value="([0-9a-f]+)"', r.get_data(as_text=True)).group(1)

    def login(self, name="boss", pw="correct horse"):
        return self.c.post("/login", data={"user": name, "password": pw, "csrf": self.csrf()})

    def post(self, path, page=None, **data):
        data["csrf"] = self.csrf(page or "/")
        return self.c.post(path, data=data)


class Auth(Base):
    def test_everything_needs_login_in_both_mode(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_bad_login_and_lockout(self):
        for _ in range(webapp.LOGIN_TRIES):
            self.assertEqual(self.login(pw="wrong").status_code, 401)
        self.assertEqual(self.login().status_code, 429)   # even the right password is refused while locked

    def test_good_login_shows_worlds(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertIn("valheim01-Test", self.c.get("/").get_data(as_text=True))

    def test_post_without_csrf_is_refused(self):
        self.login()
        r = self.c.post("/world/1/action/stop", data={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.runner.calls, [])

    def test_viewer_cannot_act(self):
        self.login("kid", "another phrase")
        r = self.post("/world/1/action/stop")
        self.assertEqual(r.status_code, 403)
        self.assertFalse([c for c in self.runner.calls if c[0][0] == "stop"])
        self.assertNotIn("Save password", self.c.get("/world/1").get_data(as_text=True))

    def test_open_redirect_is_blocked(self):
        r = self.c.post("/login", data={"user": "boss", "password": "correct horse", "csrf": self.csrf(), "next": "//evil.example"})
        self.assertEqual(r.headers["Location"].endswith("evil.example"), False)

    def test_security_headers(self):
        r = self.c.get("/login")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])


class Actions(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def last(self):
        return self.runner.calls[-1]

    def test_stop_calls_valheimctl_with_yes(self):
        self.post("/world/1/action/stop")
        self.assertEqual(self.last()[0], ["stop", "1", "--yes"])

    def test_refusal_text_is_shown(self):
        self.runner.fail = "stop"
        self.post("/world/1/action/stop")
        self.assertIn("2 player(s) connected", self.c.get("/world/1").get_data(as_text=True))

    def test_unknown_action_and_bad_world(self):
        self.assertEqual(self.post("/world/1/action/rm").status_code, 404)
        self.assertEqual(self.c.get("/world/0").status_code, 404)
        self.assertEqual(self.c.get("/world/../x").status_code, 404)

    def test_typed_password_goes_by_stdin(self):
        self.post("/world/1/password", mode="own", password="hunter22", again="hunter22")
        self.assertEqual(self.runner.calls[0], (["passwd", "1", "server"], "hunter22"))
        self.assertFalse([c for c in self.runner.calls if "hunter22" in " ".join(c[0])])

    def test_password_mismatch_and_too_short(self):
        self.post("/world/1/password", mode="own", password="hunter22", again="hunter23")
        self.post("/world/1/password", mode="own", password="abc", again="abc")
        self.assertFalse([c for c in self.runner.calls if c[0][0] == "passwd"])

    def test_generated_password_shown_once(self):
        r = self.post("/world/1/password", mode="generate")
        body = r.get_data(as_text=True)
        pw = self.runner.calls[0][1]
        self.assertEqual(self.runner.calls[0][0], ["passwd", "1", "server"])
        self.assertGreaterEqual(len(pw), 12)
        self.assertIn(pw, body)
        self.assertNotIn(pw, self.c.get("/world/1").get_data(as_text=True))   # gone on the next page view

    def test_use_default(self):
        self.post("/world/1/password", mode="default")
        self.assertEqual(self.runner.calls[0][0], ["passwd", "1", "server", "--use-default", "--yes"])

    def test_apply_now_applies_after_saving(self):
        self.post("/world/1/password", mode="own", password="hunter22", again="hunter22", apply_now="yes")
        self.assertEqual([c[0][0] for c in self.runner.calls if c[0][0] in ("passwd", "apply")], ["passwd", "apply"])

    def test_settings_keep_order_and_other_args(self):
        self.post("/world/1/settings", preset="easy", raids="none", listed="yes")
        args = self.runner.calls[0][0]
        self.assertEqual(args[:2], ["set", "1"])
        self.assertIn("SERVER_ARGS=-preset easy -modifier raids none", args)
        self.assertIn("SERVER_PUBLIC=true", args)
        self.assertIn("--no-apply", args)

    def test_settings_reject_unknown_values(self):
        self.assertEqual(self.post("/world/1/settings", preset="evil; rm", raids="").status_code, 400)

    def test_restore_needs_the_typed_word(self):
        self.post("/world/1/restore", id="snap-1", confirm="yes please")
        self.assertFalse([c for c in self.runner.calls if c[0][0] == "restore"])
        self.post("/world/1/restore", id="snap-1", confirm="restore")
        self.assertEqual(self.runner.calls[-1][0], ["restore", "1", "snap-1", "--yes"])

    def test_restore_rejects_odd_ids(self):
        self.assertEqual(self.post("/world/1/restore", id="x; rm -rf /", confirm="RESTORE").status_code, 400)

    def test_backups_page_lists_restore_points(self):
        self.assertIn("snap-1", self.c.get("/world/1/backups").get_data(as_text=True))


class AdminOnlyMode(Base):
    auth = "admin"

    def test_anonymous_can_read_but_not_act(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/world/1").status_code, 200)
        r = self.post("/world/1/action/stop", page="/login")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertFalse([c for c in self.runner.calls if c[0][0] == "stop"])

    def test_admin_login_gives_control(self):
        self.login()
        self.post("/world/1/action/start")
        self.assertEqual(self.runner.calls[-1][0], ["start", "1", "--yes"])


class NoAuthMode(unittest.TestCase):
    def test_refuses_to_start_without_the_flag_file(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "config"))
            with open(os.path.join(d, "config", "web.env"), "w") as fh:
                fh.write("WEB_AUTH=none\n")
            self.assertIn("NO_AUTH_ON_PURPOSE.flag", webapp.Settings(d).problem())
            os.makedirs(os.path.join(d, "config", "web"))
            open(os.path.join(d, "config", "web", "NO_AUTH_ON_PURPOSE.flag"), "w").close()
            self.assertIsNone(webapp.Settings(d).problem())
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_everyone_is_admin(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "config", "web"))
            with open(os.path.join(d, "config", "web.env"), "w") as fh:
                fh.write("WEB_AUTH=none\n")
            r = FakeRunner()
            c = webapp.create_app(d, r).test_client()
            self.assertEqual(c.get("/").status_code, 200)
            self.assertIn("Control", c.get("/world/1").get_data(as_text=True))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Ports(unittest.TestCase):
    def test_default_port_is_the_blocks_first_port(self):
        for fleet, want in (("", 2000), ("PORT_BLOCK=2\n", 2200), ("HONOR_ORIGINAL_PORTS=true\n", 2446)):
            d = tempfile.mkdtemp()
            try:
                os.makedirs(os.path.join(d, "config"))
                with open(os.path.join(d, "config", "fleet.env"), "w") as fh:
                    fh.write(fleet)
                self.assertEqual(webapp.Settings(d).port, want)
            finally:
                shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
