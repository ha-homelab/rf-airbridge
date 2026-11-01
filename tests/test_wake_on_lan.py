"""Check that optional network wake never changes the RF receiver or auto-wakes."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]


class SecretLoader(yaml.SafeLoader):
    pass


SecretLoader.add_constructor("!secret", lambda loader, node: ("secret", loader.construct_scalar(node)))


class WakeOnLanTest(unittest.TestCase):
    def test_opt_in_package_only_adds_explicit_network_action(self):
        for filename, target, action_name in (("wake-on-lan.yaml", "living", "wake_living_tv"),
                                              ("wake-on-lan-lg2.yaml", "lg2", "wake_lg2")):
            with self.subTest(filename=filename):
                package = yaml.load((ROOT / "packages" / filename).read_text(), Loader=SecretLoader)
                # No on_boot, on_connect, buttons, radio settings, or MQTT subscription.
                self.assertEqual(set(package), {"substitutions", "esphome", "api"})
                self.assertEqual(set(package["esphome"]), {"includes"})
                variable, secret = f"{target}_tv_wol_mac", f"{target}_tv_mac_address"
                self.assertEqual(package["substitutions"], {variable: ("secret", secret)})
                self.assertEqual(package["esphome"]["includes"], [
                    "${rf_airbridge_path}/include/wol_packet.h",
                    "${rf_airbridge_path}/include/wifi_wake.h",
                ])
                self.assertEqual(len(package["api"]["actions"]), 1)
                action = package["api"]["actions"][0]
                self.assertEqual(action["action"], action_name)
                self.assertNotIn("variables", action)
                code = action["then"][0]["lambda"]
                self.assertIn('static_assert(rf_bridge::wol::valid_mac("${' + variable + '}"),', code)
                self.assertIn('rf_bridge::wol::magic_packet("${' + variable + '}")', code)
                self.assertIn("rf_bridge::wol::send_magic_packet(packet)", code)

    def test_default_rf_config_does_not_enable_network_wake(self):
        for name in ("packages/rf-airbridge.yaml", "device.example.yaml"):
            with self.subTest(name=name):
                source = (ROOT / name).read_text()
                self.assertNotIn("wake-on-lan.yaml", source)
                self.assertNotIn("living_tv_mac_address", source)
                self.assertNotIn("wake-on-lan-lg2.yaml", source)
                self.assertNotIn("lg2_tv_mac_address", source)

    def test_validator_stages_each_optional_package_and_both_without_device_io(self):
        spec = importlib.util.spec_from_file_location("validate_firmware", ROOT / "tools/validate_firmware.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        for living, lg2 in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(living=living, lg2=lg2):
                args = ["validate_firmware", "--config-only"]
                if living:
                    args.append("--with-wake-on-lan")
                if lg2:
                    args.append("--with-lg2-wake-on-lan")

                def inspect_staging(command):
                    self.assertEqual(command[1:4], ["-m", "esphome", "config"])
                    path = Path(command[4])
                    source = path.read_text()
                    self.assertEqual("living_tv_wake:" in source, living)
                    self.assertEqual("lg2_tv_wake:" in source, lg2)
                    self.assertIn("rf_airbridge: !include packages/rf-airbridge.yaml", source)
                    secrets = yaml.safe_load(path.with_name("secrets.yaml").read_text())
                    self.assertEqual("living_tv_mac_address" in secrets, living)
                    self.assertEqual("lg2_tv_mac_address" in secrets, lg2)
                    if living and lg2:
                        self.assertNotEqual(secrets["living_tv_mac_address"], secrets["lg2_tv_mac_address"])
                    self.assertEqual(secrets["wifi_ssid"], "RF-AIRBRIDGE-VALIDATION-ONLY")
                    return SimpleNamespace(returncode=0)

                with mock.patch.object(validator.sys, "argv", args), \
                        mock.patch.object(validator.subprocess, "run", side_effect=inspect_staging) as run:
                    self.assertEqual(validator.main(), 0)
                    run.assert_called_once()

    def test_production_packet_bytes_and_rejected_addresses(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "A native C++ compiler is required")
        harness = r'''
#include "wol_packet.h"
#include <cassert>
using namespace rf_bridge::wol;
static_assert(valid_mac("02:AB:cd:00:12:34"));
static_assert(!valid_mac("02:AB:CD:00:12"));
static_assert(!valid_mac("02:AB:CD:00:12:34:56"));
static_assert(!valid_mac("02-AB-CD-00-12-34"));
static_assert(!valid_mac("02:AB:CD:00:12:3G"));
static_assert(!valid_mac("01:00:00:00:00:01"));
static_assert(!valid_mac("FF:FF:FF:FF:FF:FF"));
static_assert(!valid_mac("00:00:00:00:00:00"));
static_assert(!valid_mac(""));
int main() {
  constexpr auto packet = magic_packet("02:AB:cd:00:12:34");
  constexpr uint8_t mac[] = {2, 171, 205, 0, 18, 52};
  static_assert(packet.size() == 102);
  for (unsigned i = 0; i < 6; ++i) assert(packet[i] == 255);
  for (unsigned i = 6; i < packet.size(); ++i) assert(packet[i] == mac[(i - 6) % 6]);
  constexpr auto second = magic_packet("02:AB:cd:00:12:35");
  for (unsigned i = 0; i < second.size(); ++i) {
    assert(second[i] == ((i >= 6 && (i - 6) % 6 == 5) ? 53 : packet[i]));
  }
  for (auto byte : magic_packet("invalid")) assert(byte == 0);
}
'''
        with tempfile.TemporaryDirectory(prefix="rf-wol-test-") as directory:
            source = Path(directory) / "test.cpp"
            binary = Path(directory) / "test"
            source.write_text(harness)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "include"), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
