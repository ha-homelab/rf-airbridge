"""Exercise the real package templates without an HA instance or any RF I/O.

Uses Jinja2 and PyYAML. These tests do not replace Home Assistant's configuration
check or an installed-runtime test: they isolate matching and input validation.
"""

import json
from pathlib import Path
import re
import unittest

import jinja2
import yaml


PACKAGE = Path(__file__).resolve().parents[1] / "examples" / "home-assistant.yaml"


def from_json(value, default=None):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


class HomeAssistantTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = yaml.safe_load(PACKAGE.read_text())
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        # These two HA filters are the only non-Jinja filters in the templates.
        env.filters["from_json"] = from_json
        env.filters["regex_match"] = lambda value, pattern: re.match(pattern, value) is not None
        automation = cls.package["automation"][0]
        script = cls.package["script"]["rf_send_code"]
        cls.receive = env.from_string(automation["conditions"][0]["value_template"])
        cls.reject_transmit = env.from_string(script["sequence"][0]["if"][0]["value_template"])
        cls.packet = {
            "source": "rf",
            "origin": "radio",
            "format": "rc_switch",
            "protocol": 1,
            "bits": 24,
            "code": "000000010010001101000101",
        }

    def receive_matches(self, payload):
        return self.receive.render(trigger={"payload": payload}).strip() == "True"

    def transmit_rejected(self, **fields):
        return self.reject_transmit.render(**fields).strip() == "True"

    def test_valid_receive_matches_with_or_without_observation_metadata(self):
        self.assertTrue(self.receive_matches(json.dumps(self.packet)))
        packet = dict(self.packet, sequence=19, uptime_ms=12345, event_id="synthetic-test")
        self.assertTrue(self.receive_matches(json.dumps(packet)))

    def test_unrelated_or_malformed_payload_is_ignored(self):
        for raw in ("not JSON", "", "null", "[]", '"text"', "1", "true", "{}"):
            with self.subTest(raw=raw):
                self.assertFalse(self.receive_matches(raw))
        alternatives = {
            "source": ["other", None],
            "origin": ["transmit", None],
            "format": ["raw", None],
            "protocol": [2, "1", True, 1.0, None],
            "bits": [23, "24", 24.0, None],
            "code": ["100000010010001101000101", "10010001101000101", 74565, None],
        }
        for key, values in alternatives.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    packet = dict(self.packet, **{key: value})
                    self.assertFalse(self.receive_matches(json.dumps(packet)))
            packet = dict(self.packet)
            del packet[key]
            with self.subTest(missing=key):
                self.assertFalse(self.receive_matches(json.dumps(packet)))

    def test_valid_transmit_boundaries_and_default_repeats(self):
        for code in ("0" * 8, "1" * 64, self.packet["code"]):
            for protocol in (1, 8):
                for repeats in (1, 10):
                    with self.subTest(code=code, protocol=protocol, repeats=repeats):
                        self.assertFalse(self.transmit_rejected(
                            code=code, protocol=protocol, repeats=repeats
                        ))
        self.assertFalse(self.transmit_rejected(code=self.packet["code"], protocol=1))

    def test_invalid_transmit_fields_rejected_before_action(self):
        valid = {"code": self.packet["code"], "protocol": 1, "repeats": 3}
        alternatives = {
            "code": ["", "0" * 7, "1" * 65, "00000002", "00000000\n", " 00000000", 12345678, None, True],
            "protocol": [0, 9, -1, 1.5, "no", True, False, None],
            "repeats": [0, 11, -1, 2.5, "no", True, False, None],
        }
        for key, values in alternatives.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertTrue(self.transmit_rejected(**dict(valid, **{key: value})))
        for missing in ("code", "protocol"):
            fields = dict(valid)
            del fields[missing]
            with self.subTest(missing=missing):
                self.assertTrue(self.transmit_rejected(**fields))

    def test_receive_example_has_no_physical_output(self):
        actions = self.package["automation"][0]["actions"]
        self.assertEqual(actions[0]["action"], "counter.increment")
        self.assertEqual(actions[0]["target"]["entity_id"], "counter.rf_received_example")
        self.assertEqual(actions[1], {"delay": {"milliseconds": 750}})
        self.assertEqual(len(actions), 2)


if __name__ == "__main__":
    unittest.main()
