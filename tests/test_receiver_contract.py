"""Native tests of the bridge contract, not the ESPHome RF waveform decoder.

The decoder double returns deliberately chosen decoded values, including a
64-bit code and a code with leading zeroes. This isolates serialization and
delivery policy. Compile the actual ESPHome firmware separately.
"""

import json
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SANITIZER_FLAGS = (
    ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-g", "-O1"]
    if os.environ.get("RF_CPP_SANITIZERS") == "1" else []
)

DECODER_DOUBLE = r"""
#pragma once
#include <cstdint>
#include <vector>
namespace esphome::remote_base {
using RawTimings = std::vector<int32_t>;
enum ToleranceMode { TOLERANCE_MODE_PERCENTAGE };
struct RemoteReceiveData {
  const RawTimings &timings;
  RemoteReceiveData(const RawTimings &t, uint32_t, ToleranceMode) : timings(t) {}
  void reset() {}
};
struct RCSwitchBase {
  int protocol;
  bool decode(RemoteReceiveData &input, uint64_t *value, uint8_t *bits) const {
    if (input.timings.empty()) return false;
    if (input.timings[0] == 900024 && (protocol == 1 || protocol == 2)) {
      *value = 5;
      *bits = 24;
      return true;
    }
    if (input.timings[0] == 900064 && protocol == 8) {
      *value = UINT64_MAX;
      *bits = 64;
      return true;
    }
    return false;
  }
};
inline const RCSwitchBase RC_SWITCH_PROTOCOLS[9] = {{0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, {8}};
}
"""

HAL_DOUBLE = r"""
#pragma once
#include <cstdint>
namespace esphome {
inline uint32_t test_now = 0;
inline uint32_t millis() { return test_now; }
}
"""

HELPERS_DOUBLE = r"""
#pragma once
#include <cstdint>
namespace esphome {
inline uint32_t random_uint32() { static uint32_t value = 0x12340000; return value++; }
}
"""

HARNESS = r"""
// ESPHome declares HAL functions before defining compatibility macros in the
// generated main.cpp. Preserve that order so this reproduces the real build's
// function-like millis macro without corrupting the stub function declaration.
#include "esphome/core/hal.h"
#define millis() esphome::millis()
#include "rf_receiver.h"
#include <cassert>
#include <iostream>
#include <string>
#include <vector>

struct Message {
  std::string topic;
  std::string payload;
};
struct Sink {
  bool connected = true;
  bool success = true;
  std::vector<Message> messages;
  bool is_connected() { return connected; }
  bool publish(const char *topic, const char *data, size_t length, uint8_t qos, bool retain) {
    assert(qos == 0);
    assert(!retain);
    assert(length < rf_bridge::Receiver::MAX_PAYLOAD_BYTES);
    messages.push_back({topic, std::string(data, length)});
    return success;
  }
};
using rf_bridge::ReceiveResult;

int main() {
  rf_bridge::Receiver receiver;
  Sink sink;
  const esphome::remote_base::RawTimings known{900024};
  const esphome::remote_base::RawTimings unknown{500, -1500, 1500, -4000};

  assert(receiver.on_receive(known, sink) == ReceiveResult::DECODED_PUBLISHED);
  assert(receiver.on_receive(known, sink, true) == ReceiveResult::DECODED_PUBLISHED);
  assert(receiver.on_receive({900064}, sink) == ReceiveResult::DECODED_PUBLISHED);
  assert(sink.messages.size() == 3);
  for (const auto &message : sink.messages) {
    assert(message.topic == "rf/received");
    std::cout << message.payload << '\n';
  }

  assert(receiver.on_receive(unknown, sink) == ReceiveResult::UNDECODED);
  assert(receiver.on_receive(known, sink, true, true) == ReceiveResult::SUPPRESSED);
  sink.connected = false;
  assert(receiver.on_receive(known, sink) == ReceiveResult::OFFLINE);
  assert(receiver.on_receive(unknown, sink, true) == ReceiveResult::OFFLINE);
  assert(sink.messages.size() == 3);
  sink.connected = true;
  // Reconnection does not flush an offline backlog.
  assert(receiver.on_receive(unknown, sink) == ReceiveResult::UNDECODED);
  assert(sink.messages.size() == 3);

  assert(receiver.on_receive(unknown, sink, true) == ReceiveResult::RAW_PUBLISHED);
  assert(sink.messages.back().topic == "rf/received/raw");
  std::cout << sink.messages.back().payload << '\n';
  assert(receiver.on_receive(unknown, sink, true) == ReceiveResult::RAW_RATE_LIMITED);
  esphome::test_now = 499;
  assert(receiver.on_receive(unknown, sink, true) == ReceiveResult::RAW_RATE_LIMITED);
  esphome::test_now = 500;
  assert(receiver.on_receive(unknown, sink, true) == ReceiveResult::RAW_PUBLISHED);

  esphome::test_now = 1000;
  assert(receiver.on_receive({}, sink, true) == ReceiveResult::RAW_OUT_OF_BOUNDS);
  assert(receiver.on_receive({0}, sink, true) == ReceiveResult::RAW_OUT_OF_BOUNDS);
  assert(receiver.on_receive({120001}, sink, true) == ReceiveResult::RAW_OUT_OF_BOUNDS);
  assert(receiver.on_receive({INT32_MIN}, sink, true) == ReceiveResult::RAW_OUT_OF_BOUNDS);
  assert(receiver.on_receive(std::vector<int32_t>(257, 500), sink, true) == ReceiveResult::RAW_OUT_OF_BOUNDS);

  // Worst permitted source and waveform lengths fit without truncation.
  rf_bridge::Receiver largest("abcdefghijklmnopqrstuvwxyz123456");
  auto worst = std::vector<int32_t>(256, -120000);
  assert(largest.on_receive(worst, sink, true) == ReceiveResult::RAW_PUBLISHED);
  std::cout << sink.messages.back().payload << '\n';

  // Rate limiting remains correct across the 32-bit millis() rollover.
  rf_bridge::Receiver rollover;
  esphome::test_now = UINT32_MAX - 99;
  assert(rollover.on_receive(unknown, sink, true) == ReceiveResult::RAW_PUBLISHED);
  esphome::test_now = 200;
  assert(rollover.on_receive(unknown, sink, true) == ReceiveResult::RAW_RATE_LIMITED);
  esphome::test_now = 400;
  assert(rollover.on_receive(unknown, sink, true) == ReceiveResult::RAW_PUBLISHED);

  rf_bridge::Receiver invalid_source("invalid\"source");
  assert(invalid_source.on_receive(known, sink) == ReceiveResult::INVALID_CONFIGURATION);
  rf_bridge::Receiver too_long("abcdefghijklmnopqrstuvwxyz1234567");
  assert(too_long.on_receive(known, sink) == ReceiveResult::INVALID_CONFIGURATION);
  rf_bridge::Receiver empty_source("");
  assert(empty_source.on_receive(known, sink) == ReceiveResult::INVALID_CONFIGURATION);
  rf_bridge::Receiver invalid_tolerance("rf", "rf/received", "rf/received/raw", 101);
  assert(invalid_tolerance.on_receive(known, sink) == ReceiveResult::INVALID_CONFIGURATION);
  sink.success = false;
  assert(receiver.on_receive(known, sink) == ReceiveResult::PUBLISH_FAILED);
  return 0;
}
"""


class ReceiverContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("c++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("A C++17 compiler is required")
        cls.temp = tempfile.TemporaryDirectory(prefix="rf-receiver-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        files = {
            "esphome/components/remote_base/rc_switch_protocol.h": DECODER_DOUBLE,
            "esphome/core/hal.h": HAL_DOUBLE,
            "esphome/core/helpers.h": HELPERS_DOUBLE,
            "test.cpp": HARNESS,
        }
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        binary = root / "receiver-test"
        subprocess.run(
            [compiler, *SANITIZER_FLAGS, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(root),
             "-I", str(ROOT / "include"), str(root / "test.cpp"), "-o", str(binary)],
            check=True, capture_output=True, text=True,
        )
        result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
        cls.messages = [json.loads(line) for line in result.stdout.splitlines()]

    def test_leading_zeroes_and_first_protocol(self):
        event = self.messages[0]
        self.assertEqual(event["code"], "000000000000000000000101")
        self.assertEqual(event["bits"], 24)
        self.assertEqual(event["value"], "5")
        self.assertEqual(event["protocol"], 1)

    def test_duplicate_frames_have_distinct_event_ids(self):
        first, second = self.messages[:2]
        self.assertEqual(first["code"], second["code"])
        self.assertEqual(first["boot_id"], second["boot_id"])
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertEqual(second["sequence"], first["sequence"] + 1)

    def test_full_width_code_is_a_lossless_string(self):
        event = self.messages[2]
        self.assertEqual(event["code"], "1" * 64)
        self.assertEqual(event["value"], "18446744073709551615")
        self.assertEqual(event["bits"], 64)
        self.assertEqual(event["protocol"], 8)

    def test_raw_timings_are_complete_and_signed(self):
        event = self.messages[3]
        self.assertEqual(event["format"], "raw")
        self.assertEqual(event["durations_us"], [500, -1500, 1500, -4000])
        self.assertEqual(event["pulse_count"], 4)

    def test_largest_permitted_payload_is_not_truncated(self):
        event = self.messages[4]
        self.assertEqual(event["pulse_count"], 256)
        self.assertEqual(event["durations_us"], [-120000] * 256)
        self.assertEqual(event["source"], "abcdefghijklmnopqrstuvwxyz123456")

    def test_metadata_is_radio_origin_with_configured_frequency(self):
        for event in self.messages:
            self.assertEqual(event["schema"], 1)
            self.assertEqual(event["origin"], "radio")
            self.assertEqual(event["frequency_mhz"], 433.92)
            self.assertEqual(len(event["boot_id"]), 16)
            self.assertEqual(event["event_id"],
                             f'{event["source"]}:{event["boot_id"]}:{event["sequence"]}')


if __name__ == "__main__":
    unittest.main()
