#!/usr/bin/env python3
"""Regression checks for dependencies required by the application entrypoint."""

import subprocess
import sys
import unittest
from pathlib import Path


class StartupDependencyTests(unittest.TestCase):
    def test_config_module_can_be_imported(self):
        result = subprocess.run(
            [sys.executable, "-c", "import config"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
