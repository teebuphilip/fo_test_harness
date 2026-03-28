#!/usr/bin/env python3

import json
import os
import sys
import unittest

THIS_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
FIXTURES_DIR = os.path.join(THIS_DIR, "fixtures")

sys.path.insert(0, ROOT_DIR)

from pass0_gap_check import (
    run_gap_check,
    DECISION_BUILD,
    DECISION_HOLD,
    DECISION_KILL,
    DECISION_REPOSITION,
)


def _load_fixture(name: str):
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestPass0GapCheck(unittest.TestCase):
    def test_hold_without_research(self):
        intake = _load_fixture("intake_hold.json")
        output = run_gap_check(intake)
        self.assertEqual(output["decision_status"], DECISION_HOLD)
        self.assertIsNotNone(output["locked_fields"]["primary_user"])

    def test_kill_missing_required_fields(self):
        intake = _load_fixture("intake_kill.json")
        output = run_gap_check(intake)
        self.assertEqual(output["decision_status"], DECISION_KILL)
        self.assertTrue(output["locked_fields"]["must_not_build"])

    def test_build_with_research(self):
        intake = _load_fixture("intake_build.json")
        research_path = os.path.join(FIXTURES_DIR, "research_build.json")
        output = run_gap_check(intake, research_from_file=research_path)
        self.assertEqual(output["decision_status"], DECISION_BUILD)
        self.assertIsNotNone(output["one_liner"])

    def test_reposition_with_high_saturation(self):
        intake = _load_fixture("intake_reposition.json")
        research_path = os.path.join(FIXTURES_DIR, "research_reposition.json")
        output = run_gap_check(intake, research_from_file=research_path)
        self.assertEqual(output["decision_status"], DECISION_REPOSITION)
        self.assertIsNone(output["one_liner"])


if __name__ == "__main__":
    unittest.main()
