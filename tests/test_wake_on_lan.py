"""Check that optional network wake never changes the RF receiver or auto-wakes."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class SecretLoader(yaml.SafeLoader):
    pass


SecretLoader.add_constructor("!secret", lambda loader, node: ("secret", loader.construct_scalar(node)))


class WakeOnLanTest(unittest.TestCase):
    def test_opt_in_package_only_adds_explicit_network_action(self):
        package = yaml.load((ROOT / "packages/wake-on-lan.yaml").read_text(), Loader=SecretLoader)
        # No on_boot, on_connect, radio settings, or MQTT command subscription.
        self.assertEqual(set(package), {"substitutions", "esphome", "api"})
        self.assertEqual(set(package["esphome"]), {"includes"})
        self.assertEqual(package["substitutions"]["living_tv_wol_mac"],
                         ("secret", "living_tv_mac_address"))
        self.assertEqual(len(package["api"]["actions"]), 1)
        action = package["api"]["actions"][0]
        self.assertEqual(action["action"], "wake_living_tv")
        self.assertNotIn("variables", action)
        self.assertIn("static_assert", action["then"][0]["lambda"])

    def test_default_rf_config_does_not_enable_network_wake(self):
        for name in ("packages/rf-airbridge.yaml", "device.example.yaml"):
            with self.subTest(name=name):
                source = (ROOT / name).read_text()
                self.assertNotIn("wake-on-lan.yaml", source)
                self.assertNotIn("living_tv_mac_address", source)

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
