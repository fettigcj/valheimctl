#!/usr/bin/env python3
# Copyright (C) 2026 Chris Fettig
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the menu's logic (no terminal needed). Run: python3 tests/test_menu.py"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("menu", os.path.join(HERE, "..", "tui", "menu.py"))
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class ServerArgs(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(menu.parse_server_args("-preset hard -modifier raids none -crossplay"),
                         ("hard", {"raids": "none"}, ["-crossplay"]))

    def test_parse_empty(self):
        self.assertEqual(menu.parse_server_args(""), ("", {}, []))

    def test_preset_always_before_modifiers(self):
        # the game rule: a preset overwrites modifiers, so it must come first
        self.assertEqual(menu.build_server_args("hard", {"raids": "none"}, []), "-preset hard -modifier raids none")
        self.assertEqual(menu.with_preset("-modifier raids none", "easy"), "-preset easy -modifier raids none")

    def test_raids_set_and_clear(self):
        self.assertEqual(menu.with_raids("", "none"), "-modifier raids none")
        self.assertEqual(menu.with_raids("-modifier raids none", ""), "")
        self.assertEqual(menu.with_raids("-preset hard -foo", "more"), "-preset hard -modifier raids more -foo")

    def test_other_modifiers_and_tokens_survive(self):
        a = "-modifier combat hard -modifier raids none -setkey nomap"
        out = menu.with_raids(a, "less")
        self.assertIn("-modifier combat hard", out)
        self.assertIn("-modifier raids less", out)
        self.assertTrue(out.endswith("-setkey nomap"))
        self.assertNotIn("none", out)

    def test_round_trip(self):
        a = "-preset hard -modifier raids none"
        self.assertEqual(menu.build_server_args(*menu.parse_server_args(a)), a)


class Ports(unittest.TestCase):
    def test_default_block(self):
        self.assertEqual(menu.world_ports(1), (2010, 2011))
        self.assertEqual(menu.world_ports(9), (2090, 2091))

    def test_blocks(self):
        self.assertEqual(menu.world_ports(1, 1), (2110, 2111))
        self.assertEqual(menu.world_ports(3, 2), (2230, 2231))

    def test_honor_original(self):
        self.assertEqual(menu.world_ports(1, 0, True), (2456, 2457))
        self.assertEqual(menu.world_ports(4, 0, True), (2486, 2487))


class Misc(unittest.TestCase):
    def test_free_worlds(self):
        self.assertEqual(menu.free_world_numbers([1, 2, 4]), [3, 5, 6, 7, 8, 9])
        self.assertEqual(menu.free_world_numbers(range(1, 10)), [])

    def test_env_parse(self):
        t = '# c\nA=1\n\nB="two words"\nlower=x\nC=\n'
        self.assertEqual(menu.parse_env_text(t), {"A": "1", "B": "two words", "C": ""})

    def test_validators(self):
        self.assertTrue(menu.SUFFIX_RE.match("Kid-World_2"))
        self.assertFalse(menu.SUFFIX_RE.match("kid world"))
        self.assertTrue(menu.INSTANCE_RE.match("testdocker"))
        self.assertFalse(menu.INSTANCE_RE.match("testDocker"))

    def test_labels(self):
        self.assertEqual(menu.choice_label(menu.RAIDS, "none"), "None")
        self.assertEqual(menu.choice_label(menu.RAIDS, ""), "Game default")

    def test_local_time_keeps_bad_input(self):
        self.assertEqual(menu.local_time("not a time"), "not a time")
        self.assertRegex(menu.local_time("2026-10-09 11:29:15"), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_world_number_from_file(self):
        self.assertEqual(menu.parse_world_number("04.env"), 4)
        self.assertIsNone(menu.parse_world_number("04.env.removed-20261010"))
        self.assertIsNone(menu.parse_world_number("10.env"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
