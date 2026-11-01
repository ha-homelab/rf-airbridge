"""Check that optional network wake never changes the RF receiver or auto-wakes."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SANITIZER_FLAGS = (
    ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-g", "-O1"]
    if os.environ.get("RF_CPP_SANITIZERS") == "1" else []
)


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
                self.assertEqual(len(action["then"]), 1)
                repeat = action["then"][0]["repeat"]
                self.assertEqual(repeat["count"], 3)
                self.assertEqual(len(repeat["then"]), 2)
                self.assertEqual(repeat["then"][1], {"delay": "250ms"})
                code = repeat["then"][0]["lambda"]
                self.assertIn("rf_bridge::wol::send_subnet_magic_packet(packet)", code)
                self.assertIn('static_assert(rf_bridge::wol::valid_mac("${' + variable + '}"),', code)
                self.assertIn('rf_bridge::wol::magic_packet("${' + variable + '}")', code)
                self.assertNotIn("delay(", code)

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
            subprocess.run([compiler, *SANITIZER_FLAGS, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "include"), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_directed_broadcast_uses_station_mask_and_preserves_legacy_helper(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "A native C++ compiler is required")
        support = r'''
#pragma once
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
class IPAddress {
 public:
  std::array<uint8_t,4> bytes{};
  IPAddress() = default;
  IPAddress(uint8_t a,uint8_t b,uint8_t c,uint8_t d):bytes{a,b,c,d}{}
  uint8_t operator[](size_t i) const { return bytes[i]; }
  bool is_ip4() const { return true; }
  bool operator==(const IPAddress &other) const { return bytes==other.bytes; }
};
struct FakeWiFi {
  IPAddress address{192,168,160,206};
  IPAddress mask{255,255,240,0};
  IPAddress localIP() const { return address; }
  IPAddress subnetMask() const { return mask; }
};
inline FakeWiFi WiFi;
struct Frame { IPAddress destination; std::vector<uint8_t> bytes; };
inline std::vector<Frame> frames;
inline bool connected=true, begin_ok=true, write_ok=true, end_ok=true;
class WiFiUDP {
  Frame frame;
 public:
  int beginPacketMulticast(IPAddress destination,uint16_t port,IPAddress,int ttl) {
    assert(port==9 && ttl==128); frame.destination=destination; return begin_ok;
  }
  size_t write(const uint8_t *data,size_t size) {
    frame.bytes.assign(data,data+size); return write_ok ? size : 0;
  }
  int endPacket() { frames.push_back(frame); return end_ok; }
};
namespace esphome::network {
  inline bool is_connected() { return connected; }
  inline std::array<IPAddress,1> get_ip_addresses() { return {WiFi.address}; }
}
#define ESP_LOGW(tag,...) ((void)(tag))
#define ESP_LOGI(tag,...) ((void)(tag))
'''
        harness = r'''
#include "wifi_wake.h"
using namespace rf_bridge::wol;
int main() {
  constexpr auto packet=magic_packet("02:AB:CD:00:12:35");
  assert(send_magic_packet(packet));
  assert(frames.size()==1 && frames.back().destination==IPAddress(255,255,255,255));
  assert(send_subnet_magic_packet(packet));
  assert(frames.size()==2 && frames.back().destination==IPAddress(192,168,175,255));
  assert(frames.back().bytes==std::vector<uint8_t>(packet.begin(),packet.end()));
  WiFi.address=IPAddress(172,16,6,3); WiFi.mask=IPAddress(255,255,254,0);
  assert(send_subnet_magic_packet(packet));
  assert(frames.back().destination==IPAddress(172,16,7,255));
  WiFi.address=IPAddress(10,42,3,4); WiFi.mask=IPAddress(255,255,0,0);
  assert(send_subnet_magic_packet(packet));
  assert(frames.back().destination==IPAddress(10,42,255,255));
  const auto sent=frames.size();
  for (auto mask:{IPAddress(0,0,0,0),IPAddress(255,255,255,255),
                  IPAddress(255,255,255,254),IPAddress(255,0,255,0)}) {
    WiFi.mask=mask; assert(!send_subnet_magic_packet(packet));
  }
  WiFi.mask=IPAddress(255,255,240,0);
  for (auto address:{IPAddress(0,0,0,0),IPAddress(224,0,0,1),
                     IPAddress(192,168,160,0),IPAddress(192,168,175,255)}) {
    WiFi.address=address; assert(!send_subnet_magic_packet(packet));
  }
  assert(frames.size()==sent);
  WiFi.address=IPAddress(192,168,160,206);
  connected=false; assert(!send_subnet_magic_packet(packet));
  connected=true; begin_ok=false; assert(!send_subnet_magic_packet(packet));
  assert(frames.size()==sent);
  begin_ok=true; write_ok=false; assert(!send_subnet_magic_packet(packet));
  write_ok=true; end_ok=false; assert(!send_subnet_magic_packet(packet));
  end_ok=true; WiFi.mask=IPAddress(0,0,0,0);
  assert(send_magic_packet(packet)); // Legacy low-level helper remains available to custom configurations.
  assert(frames.back().destination==IPAddress(255,255,255,255));
}
'''
        with tempfile.TemporaryDirectory(prefix="rf-wol-transport-test-") as directory:
            temporary = Path(directory)
            (temporary / "fake_platform.h").write_text(support)
            for name in ("ESP8266WiFi.h", "WiFiUdp.h", "esphome/components/network/util.h", "esphome/core/log.h"):
                path = temporary / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#include "fake_platform.h"\n')
            source, binary = temporary / "test.cpp", temporary / "test"
            source.write_text(harness)
            subprocess.run([compiler, *SANITIZER_FLAGS, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(temporary), "-I", str(ROOT / "include"),
                            str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
