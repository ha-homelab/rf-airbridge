"""Check the real package's cross-format routing and busy/cooldown contract.

These tests inspect the actual ESPHome action graph; they do not claim to
simulate its scheduler or prove radio delivery. The full example build checks
that the actions and lambda types compile against ESPHome 2026.8.2.
"""

from pathlib import Path
import unittest

import yaml


class ESPHomeLoader(yaml.SafeLoader):
    pass


ESPHomeLoader.add_constructor("!lambda", lambda loader, node: loader.construct_scalar(node))
PACKAGE = Path(__file__).resolve().parents[1] / "packages" / "rf-airbridge.yaml"


class SharedTransmitterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = yaml.load(PACKAGE.read_text(), Loader=ESPHomeLoader)
        cls.actions = {action["action"]: action for action in cls.package["api"]["actions"]}
        cls.workers = {worker["id"]: worker for worker in cls.package["script"]}

    def test_both_formats_validate_then_enter_the_same_guarded_worker(self):
        destinations = []
        for name, validator, is_dooya in (
            ("send_rf_code", "valid_tx_request", False),
            ("send_dooya_code", "valid_dooya_request", True),
        ):
            with self.subTest(action=name):
                actions = self.actions[name]["then"]
                self.assertEqual(len(actions), 1)
                validation = actions[0]["if"]
                self.assertIn(validator, validation["condition"]["lambda"])
                self.assertEqual(len(validation["then"]), 1)
                guard = validation["then"][0]["if"]
                guarded_worker = guard["condition"]["not"]["script.is_running"]
                self.assertEqual(len(guard["then"]), 1)
                execution = guard["then"][0]["script.execute"]
                self.assertEqual(execution["id"], guarded_worker)
                self.assertEqual(execution["is_dooya"], is_dooya)
                destinations.append(guarded_worker)
                self.assertEqual(set(execution) - {"id"}, set(self.workers[guarded_worker]["parameters"]))
        self.assertEqual(len(set(destinations)), 1, "Separate workers permit cross-format overlap")

    def test_shared_worker_holds_busy_until_after_completion_and_cooldown(self):
        destination = self.actions["send_dooya_code"]["then"][0]["if"]["then"][0]["if"]["then"][0]["script.execute"]["id"]
        worker = self.workers[destination]
        self.assertEqual(worker["mode"], "single")
        sequence = worker["then"]
        self.assertEqual(len(sequence), 3)
        self.assertIn("if", sequence[0])
        self.assertIn("mqtt.publish_json", sequence[1])
        self.assertEqual(sequence[-1], {"delay": "750ms"})
        self.assertIn('root["receiver_resumed"] = !id(rf_tx_active)', sequence[1]["mqtt.publish_json"]["payload"])

    def test_both_encoders_use_the_same_transmitter_and_ten_ms_repeat_gap(self):
        worker = next(worker for worker in self.workers.values() if "is_dooya" in worker["parameters"])
        branch = worker["then"][0]["if"]
        self.assertEqual(branch["condition"]["lambda"], "return is_dooya;")
        for side, encoder in (("then", "transmit_dooya"), ("else", "transmit_rc_switch_raw")):
            with self.subTest(encoder=encoder):
                self.assertEqual(len(branch[side]), 1)
                transmit = branch[side][0]["remote_transmitter." + encoder]
                self.assertEqual(transmit["transmitter_id"], self.package["remote_transmitter"]["id"])
                self.assertEqual(transmit["repeat"], {"times": "return repeats;", "wait_time": "10ms"})
        dooya = branch["then"][0]["remote_transmitter.transmit_dooya"]
        self.assertEqual(dooya["id"], "return remote_id;")
        for field in ("channel", "button", "check"):
            self.assertEqual(dooya[field], f"return {field};")

    def test_dooya_service_and_result_contract(self):
        action = self.actions["send_dooya_code"]
        self.assertEqual(action["variables"], dict.fromkeys(
            ["remote_id", "channel", "button", "check", "repeats"], "int"))
        validation = action["then"][0]["if"]
        guard = validation["then"][0]["if"]
        for status, result in (
            ("invalid_request", validation["else"][0]["mqtt.publish_json"]),
            ("busy", guard["else"][0]["mqtt.publish_json"]),
        ):
            with self.subTest(status=status):
                self.assertEqual(result["qos"], 0)
                self.assertIs(result["retain"], False)
                self.assertIn('root["format"] = "dooya";', result["payload"])
                self.assertIn(f'root["status"] = "{status}";', result["payload"])
                self.assertIn('root["delivery_confirmed"] = false;', result["payload"])
        worker = next(worker for worker in self.workers.values() if "is_dooya" in worker["parameters"])
        completion = worker["then"][1]["mqtt.publish_json"]
        self.assertEqual(completion["qos"], 0)
        self.assertIs(completion["retain"], False)
        self.assertIn('root["format"] = is_dooya ? "dooya" : "rc_switch";', completion["payload"])
        self.assertIn('root["delivery_confirmed"] = false;', completion["payload"])

    def test_dooya_does_not_change_the_existing_receiver_timing(self):
        receiver = self.package["remote_receiver"]
        self.assertEqual(receiver["dump"], "rc_switch")
        self.assertEqual(receiver["tolerance"], "30%")
        self.assertEqual(receiver["filter"], "250us")
        self.assertEqual(receiver["idle"], "4ms")


if __name__ == "__main__":
    unittest.main()
