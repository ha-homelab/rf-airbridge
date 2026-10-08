"""Compile the actual ESP8266 receiver patch against small GPIO/clock doubles."""

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

STUB = r"""
#pragma once
#include <cstdint>
#include <cstdlib>
#include <vector>
#define IRAM_ATTR
#define HOT
namespace esphome {
namespace remote_receiver { struct RemoteReceiverComponentStore; }
namespace gpio {
enum Flags { FLAG_INPUT = 1, FLAG_OUTPUT = 2 };
enum InterruptType { INTERRUPT_ANY_EDGE };
}
inline uint32_t clock_us = 0;
inline uint32_t micros() { return clock_us; }
class InternalGPIOPin;
struct ISRInternalGPIOPin {
  InternalGPIOPin *pin = nullptr;
  bool digital_read();
};
class InternalGPIOPin {
 public:
  bool level = false;
  gpio::Flags mode = gpio::FLAG_INPUT;
  unsigned attached = 0, detached = 0, isr_objects = 0;
  void (*callback)(remote_receiver::RemoteReceiverComponentStore *) = nullptr;
  remote_receiver::RemoteReceiverComponentStore *context = nullptr;
  void setup() { mode = gpio::FLAG_INPUT; }
  void pin_mode(gpio::Flags next) { mode = next; }
  bool digital_read() { return level; }
  ISRInternalGPIOPin to_isr() { ++isr_objects; return {this}; }
  void attach_interrupt(void (*fn)(remote_receiver::RemoteReceiverComponentStore *),
                        remote_receiver::RemoteReceiverComponentStore *arg,
                        gpio::InterruptType) {
    ++attached; callback = fn; context = arg;
  }
  void detach_interrupt() { ++detached; callback = nullptr; context = nullptr; }
  void edge(bool next, uint32_t elapsed) {
    clock_us += elapsed; level = next;
    if (callback) callback(context);
  }
};
inline bool ISRInternalGPIOPin::digital_read() { return pin->digital_read(); }
class Component {
 public:
  bool enabled = true;
  virtual ~Component() = default;
  virtual void setup() {}
  virtual void dump_config() {}
  virtual void loop() {}
  void disable_loop() { enabled = false; }
  void enable_loop() { enabled = true; }
};
struct InterruptLock {};
struct HighFrequencyLoopRequester {
  inline static int active = 0;
  void start() { ++active; }
  void stop() { --active; }
};
namespace remote_base {
enum { TOLERANCE_MODE_PERCENTAGE, TOLERANCE_MODE_TIME };
class RemoteReceiverBase {
 public:
  explicit RemoteReceiverBase(InternalGPIOPin *pin) : pin_(pin) {}
  unsigned delivered = 0;
 protected:
  void call_listeners_dumpers_() { ++delivered; }
  InternalGPIOPin *pin_;
  std::vector<int32_t> temp_;
  uint32_t tolerance_ = 25;
  int tolerance_mode_ = TOLERANCE_MODE_PERCENTAGE;
};
}
}
"""

TEST = r"""
#include <cassert>
#include <cstddef>
#include <cstdlib>
#include <new>
#include <vector>
static size_t allocations = 0;
void *operator new(std::size_t n) {
  ++allocations;
  if (void *p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void *operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void *p) noexcept { std::free(p); }
void operator delete[](void *p) noexcept { std::free(p); }
void operator delete(void *p, std::size_t) noexcept { std::free(p); }
void operator delete[](void *p, std::size_t) noexcept { std::free(p); }
// Only the test exposes state; production code retains protected members.
#define protected public
#include "remote_receiver.cpp"
#undef protected
int main() {
  using namespace esphome;
  InternalGPIOPin pin;
  remote_receiver::RemoteReceiverComponent receiver(&pin);
  receiver.suspend();
  receiver.resume();
  assert(pin.attached == 0 && pin.detached == 0);
  receiver.set_buffer_size(128);
  receiver.set_filter_us(0);
  receiver.set_idle_us(1000);
  receiver.setup();
  auto *const original_buffer = receiver.store_.buffer;
  auto *const original_context = pin.context;
  assert(original_buffer && original_context);
  assert(HighFrequencyLoopRequester::active == 1);

  // A partial receive must not be joined to a post-transmit packet.
  pin.edge(true, 100);
  pin.edge(false, 100);
  pin.edge(true, 100);
  receiver.store_.overflow = true;
  receiver.suspend();
  receiver.suspend();
  assert(pin.detached == 1 && !pin.callback && !receiver.enabled);
  assert(HighFrequencyLoopRequester::active == 0);
  const auto before_tx = receiver.store_.buffer_write;
  pin.pin_mode(gpio::FLAG_OUTPUT);
  for (int i = 0; i < 20; ++i) pin.edge(i % 2 == 0, 100);
  receiver.loop();
  assert(receiver.delivered == 0);
  assert(receiver.store_.buffer_write == before_tx);
  receiver.resume();
  receiver.resume();
  assert(pin.attached == 2 && pin.callback && receiver.enabled);
  assert(pin.mode == gpio::FLAG_INPUT && pin.context == original_context);
  assert(receiver.store_.buffer == original_buffer);
  assert(receiver.store_.buffer_write == 0 && receiver.store_.buffer_read == 0);
  assert(receiver.store_.buffer_start == 0 && !receiver.store_.overflow);
  assert(receiver.store_.prev_micros == micros());
  assert(receiver.store_.prev_level == pin.level);
  assert(HighFrequencyLoopRequester::active == 1);

  // Repeated transmissions do not call setup(), allocate, or unbalance requests.
  const auto before_allocations = allocations;
  for (int i = 0; i < 1000; ++i) {
    receiver.suspend(); receiver.resume();
  }
  assert(allocations == before_allocations);
  assert(pin.isr_objects == 1);
  assert(receiver.store_.buffer == original_buffer);
  assert(HighFrequencyLoopRequester::active == 1);

  // The reattached ISR can produce a fresh complete receive sequence.
  for (int i = 0; i < 12; ++i) pin.edge(i % 2 == 0, 100);
  clock_us += 2000;
  receiver.loop();
  assert(receiver.delivered == 1);
  assert(!receiver.temp_.empty());
  assert(pin.context == original_context);
  delete[] original_buffer;
}
"""


class ReceiverPatchTest(unittest.TestCase):
    def test_actual_source_suspend_resume(self):
        compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("A C++17 compiler is required")
        with tempfile.TemporaryDirectory(prefix="rf-receiver-test-") as temporary:
            directory = Path(temporary)
            for name in ["components/remote_base/remote_base.h", "core/component.h", "core/hal.h", "core/helpers.h"]:
                target = directory / "esphome" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('#include "test_stubs.h"\n')
            (directory / "esphome/core/log.h").write_text(
                "#define ESP_LOGCONFIG(...)\n#define ESP_LOGW(...)\n#define LOG_PIN(...)\n"
            )
            (directory / "test_stubs.h").write_text(STUB)
            source = directory / "test.cpp"
            source.write_text(TEST)
            output = directory / "test"
            build = subprocess.run(
                [compiler, *SANITIZER_FLAGS, "-std=c++17", "-DUSE_ESP8266", "-I", str(directory), "-I",
                 str(ROOT / "components/remote_receiver"), str(source), "-o", str(output)],
                capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
