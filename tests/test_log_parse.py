from __future__ import annotations

import unittest
from pathlib import Path

from agent_pack.log.parse import aggregate_steps, parse_plan, parse_run


class LogParseTest(unittest.TestCase):
    def test_parse_plan_skips_empty(self) -> None:
        self.assertEqual(parse_plan(["a", "", "  ", "b"]), ("a", "b"))

    def test_aggregate_steps_respects_plan_order(self) -> None:
        logs = {
            "qa": [{"status": "started", "at": "t3", "detail": ""}],
            "product": [
                {"status": "started", "at": "t1", "detail": "draft"},
                {"status": "done", "at": "t2", "detail": "locked"},
            ],
        }
        steps = aggregate_steps(("product", "designer", "qa"), logs, ["qa", "product"])
        self.assertEqual([step["name"] for step in steps], ["product", "qa"])
        self.assertEqual(steps[0]["status"], "done")
        self.assertEqual(len(steps[0]["log"]), 2)

    def test_parse_run_events_exclude_steps(self) -> None:
        path = Path(self._tmp) / "run.jsonl"
        path.write_text(
            '{"event":"started","invocation_id":"abc","profile_id":"p","request_text":"r","started_at":"2026-01-01T00:00:00Z","plan":["a"]}\n'
            '{"event":"step","invocation_id":"abc","name":"a","status":"started","at":"2026-01-01T00:01:00Z"}\n'
            '{"event":"completed","invocation_id":"abc","outcome":"done","completed_at":"2026-01-01T00:02:00Z"}\n',
            encoding="utf-8",
        )
        started, completed, plan, events, steps = parse_run(path)
        self.assertIsNotNone(started)
        self.assertIsNotNone(completed)
        self.assertEqual(plan, ("a",))
        self.assertEqual(len(events), 2)
        self.assertEqual([event["event"] for event in events], ["started", "completed"])
        self.assertEqual(len(steps), 1)
        self.assertEqual(len(steps[0]["log"]), 1)

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)
