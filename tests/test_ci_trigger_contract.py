"""Keep one PR validation path while retaining main, tag and manual qualification."""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CITriggerContractTests(unittest.TestCase):
    def test_validation_keeps_pr_main_tags_and_manual_without_path_filters(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
        # PyYAML treats the YAML 1.1 word "on" as a boolean mapping key.
        events = workflow.get("on", workflow.get(True))
        self.assertEqual(set(events), {"push", "pull_request", "workflow_dispatch"})
        self.assertIsNone(events["pull_request"])
        self.assertIsNone(events["workflow_dispatch"])
        self.assertEqual(events["push"], {"branches": ["main"], "tags": ["**"]})


if __name__ == "__main__":
    unittest.main()
