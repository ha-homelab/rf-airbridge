"""Exercise native/MQTT fanout with the real RM433 decoder and receive guard."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_receiver_contract import (
    DECODER_DOUBLE, HAL_DOUBLE, HELPERS_DOUBLE, ROOT, SANITIZER_FLAGS,
)


HARNESS = r"""
#include "esphome/core/hal.h"
#define millis() esphome::millis()
#include "rf_receiver.h"
#include <cassert>
#include <string>
#include <vector>
using rf_bridge::ReceiveResult;
using esphome::remote_base::RawTimings;

static const uint32_t CODES[8] = {0x123451, 0x123452, 0x123454, 0x123458,
                                0x123453, 0x123456, 0x12345c, 0x123459};
static std::vector<std::string> events;
static unsigned callbacks = 0;
static void native(uint32_t code) {
  ++callbacks;
  if (const char *type = rf_bridge::rm433_button_type(code, CODES))
    events.emplace_back(type);
}
struct Mqtt {
  bool connected = true;
  bool success = true;
  std::vector<std::string> messages;
  bool is_connected() { return connected; }
  bool publish(const char *topic, const char *payload, size_t size, uint8_t qos, bool retain) {
    assert(std::string(topic) == "rf/received");
    assert(qos == 0 && !retain);
    // Prove the local sink ran before a potentially failing MQTT publication.
    assert(callbacks > 0);
    messages.emplace_back(payload, size);
    return success;
  }
};
static RawTimings frame(uint32_t code) {
  RawTimings result;
  for (int bit = 23; bit >= 0; --bit) {
    const bool one = (code & (uint32_t{1} << bit)) != 0;
    result.push_back(one ? 720 : 240);
    result.push_back(one ? -240 : -720);
  }
  result.push_back(240);
  result.push_back(-4000);
  return result;
}
int main(int argc, char **argv) {
  assert(argc == 2);
  const std::string scenario = argv[1];
  rf_bridge::Receiver receiver;
  Mqtt mqtt;
  const auto first = frame(CODES[0]);
  const auto second = frame(CODES[1]);
  if (scenario == "offline") {
    mqtt.connected = false;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::OFFLINE);
    assert(events == std::vector<std::string>{"button_1"});
    assert(mqtt.messages.empty());
    // The offline press is not queued, and its RF repeats cannot become a
    // second local/MQTT press merely because the broker reconnects.
    mqtt.connected = true;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::REPEAT_SUPPRESSED);
    assert(events.size() == 1 && mqtt.messages.empty());
    assert(receiver.on_receive(second, mqtt, false, false, native) == ReceiveResult::DECODED_PUBLISHED);
    assert(events.size() == 2 && mqtt.messages.size() == 1);
    assert(mqtt.messages[0].find("\"sequence\":1,") != std::string::npos);
  } else if (scenario == "repeats") {
    esphome::test_now = UINT32_MAX - 100;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::DECODED_PUBLISHED);
    esphome::test_now = 100;
    mqtt.connected = false;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::REPEAT_SUPPRESSED);
    esphome::test_now = 449;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::REPEAT_SUPPRESSED);
    esphome::test_now = 799;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::OFFLINE);
    assert(receiver.on_receive(second, mqtt, false, false, native) == ReceiveResult::OFFLINE);
    assert((events == std::vector<std::string>{"button_1", "button_1", "button_2"}));
    assert(mqtt.messages.size() == 1);
  } else if (scenario == "guard") {
    mqtt.connected = false;
    assert(receiver.on_receive(first, mqtt, true, true, native) == ReceiveResult::SUPPRESSED);
    auto malformed = first;
    malformed[10] = INT32_MIN;
    assert(receiver.on_receive(malformed, mqtt, true, false, native) == ReceiveResult::OFFLINE);
    malformed = first;
    malformed.pop_back();
    assert(receiver.on_receive(malformed, mqtt, true, false, native) == ReceiveResult::OFFLINE);
    assert(receiver.on_receive({900024}, mqtt, false, false, native) == ReceiveResult::OFFLINE);
    assert(callbacks == 0 && events.empty() && mqtt.messages.empty());
    // Suppressed or malformed captures must not consume the press guard.
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::OFFLINE);
    assert(events.size() == 1);
  } else if (scenario == "unknown") {
    assert(receiver.on_receive(frame(0x654321), mqtt, false, false, native) == ReceiveResult::DECODED_PUBLISHED);
    assert(callbacks == 1 && events.empty() && mqtt.messages.size() == 1);
    assert(mqtt.messages[0].find("\"value\":\"6636321\"") != std::string::npos);
  } else if (scenario == "failure") {
    mqtt.success = false;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::PUBLISH_FAILED);
    assert(events.size() == 1 && mqtt.messages.size() == 1);
    mqtt.success = true;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::REPEAT_SUPPRESSED);
    assert(events.size() == 1 && mqtt.messages.size() == 1);
    assert(receiver.on_receive(second, mqtt, false, false, native) == ReceiveResult::DECODED_PUBLISHED);
    assert(events.size() == 2 && mqtt.messages.size() == 2);
  } else if (scenario == "legacy") {
    mqtt.connected = false;
    assert(receiver.on_receive(first, mqtt) == ReceiveResult::OFFLINE);
    assert(callbacks == 0);
    mqtt.connected = true;
    assert(receiver.on_receive(first, mqtt, false, false, native) == ReceiveResult::DECODED_PUBLISHED);
    const std::string expected = "{\"schema\":1,\"source\":\"rf\",\"origin\":\"radio\",\"format\":\"rm433\","
      "\"frequency_mhz\":433.92,\"boot_id\":\"1234000012340001\",\"sequence\":1,"
      "\"event_id\":\"rf:1234000012340001:1\",\"uptime_ms\":0,\"encoding\":\"rc_switch_1\","
      "\"bits\":24,\"code\":\"000100100011010001010001\",\"value\":\"1193041\",\"pulse_length_us\":240}";
    assert(mqtt.messages[0] == expected);
  } else if (scenario == "mapping") {
    mqtt.connected = false;
    for (unsigned i = 0; i < 8; ++i) {
      assert(receiver.on_receive(frame(CODES[i]), mqtt, false, false, native) == ReceiveResult::OFFLINE);
      assert(events.back() == "button_" + std::to_string(i + 1));
    }
    const uint32_t disabled[8] = {UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX,
                                  UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX};
    assert(rf_bridge::rm433_button_type(UINT32_MAX, disabled) == nullptr);
    assert(rf_bridge::rm433_button_type(0, disabled) == nullptr);
    assert(rf_bridge::rm433_button_type(CODES[0], disabled) == nullptr);
    assert(events.size() == 8 && mqtt.messages.empty());
  } else {
    assert(false);
  }
}
"""


class NativeRm433Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("c++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("A C++17 compiler is required")
        directory = tempfile.TemporaryDirectory(prefix="rf-native-tests-")
        cls.addClassCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, content in {
            "esphome/components/remote_base/rc_switch_protocol.h": DECODER_DOUBLE,
            "esphome/core/hal.h": HAL_DOUBLE,
            "esphome/core/helpers.h": HELPERS_DOUBLE,
            "test.cpp": HARNESS,
        }.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        cls.binary = root / "native-test"
        subprocess.run([
            compiler, *SANITIZER_FLAGS, "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(root), "-I", str(ROOT / "include"), str(root / "test.cpp"),
            "-o", str(cls.binary),
        ], check=True, capture_output=True, text=True)

    def run_scenario(self, scenario):
        subprocess.run([str(self.binary), scenario], check=True, capture_output=True, text=True)

    def test_offline_native_and_no_reconnect_replay(self):
        self.run_scenario("offline")

    def test_one_shared_debounce_across_mqtt_state_and_clock_rollover(self):
        self.run_scenario("repeats")

    def test_tx_malformed_and_stock_protocols_do_not_emit_native_events(self):
        self.run_scenario("guard")

    def test_unknown_remote_remains_mqtt_only(self):
        self.run_scenario("unknown")

    def test_mqtt_publish_failure_does_not_block_or_duplicate_native_event(self):
        self.run_scenario("failure")

    def test_legacy_call_and_mqtt_payload_unchanged(self):
        self.run_scenario("legacy")

    def test_exact_eight_slot_mapping_and_disabled_defaults(self):
        self.run_scenario("mapping")


if __name__ == "__main__":
    unittest.main()
