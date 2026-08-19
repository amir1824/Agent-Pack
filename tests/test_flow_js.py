from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class FlowJsTest(unittest.TestCase):
    def test_flow_js(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node not installed")
        root = Path(__file__).resolve().parents[1]
        subprocess.run(["node", "--test", "tests/flow.test.mjs"], cwd=root, check=True)
