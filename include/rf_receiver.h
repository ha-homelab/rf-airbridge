#pragma once

#include "esphome/components/remote_base/rc_switch_protocol.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"

#include <cinttypes>
#include <cstdarg>
#include <cstdio>
#include <cstring>

// Uses the stock ESPHome 2026.8.2 RCSwitch decoder. It deliberately does not
// register a replacement receiver: call it from the existing on_raw trigger.
namespace rf_bridge {

enum class ReceiveResult {
  SUPPRESSED,
  OFFLINE,
  INVALID_CONFIGURATION,
  UNDECODED,
  RAW_RATE_LIMITED,
  RAW_OUT_OF_BOUNDS,
  PAYLOAD_TOO_LARGE,
  PUBLISH_FAILED,
  DECODED_PUBLISHED,
  RAW_PUBLISHED,
};

class Receiver {
 public:
  static constexpr size_t MAX_RAW_PULSES = 256;
  static constexpr int32_t MAX_RAW_DURATION_US = 120000;
  static constexpr uint32_t RAW_INTERVAL_MS = 500;
  static constexpr size_t MAX_PAYLOAD_BYTES = 2560;

  // Arguments must have static lifetime, normally string literals. source is a
  // short identifier (1-32 ASCII letters/digits/_/-), not an arbitrary label.
  explicit Receiver(const char *source = "rf", const char *decoded_topic = "rf/received",
                    const char *raw_topic = "rf/received/raw", uint32_t tolerance_percent = 30)
      : source_(source), decoded_topic_(decoded_topic), raw_topic_(raw_topic),
        tolerance_percent_(tolerance_percent) {}

  // MqttClient may be ESPHome's MQTTClientComponent or a compatible test sink.
  // No MQTT subscription, entity publication, backlog, or RF transmission is
  // created here. suppress_rx is controlled by the caller's TX/cooldown guard.
  template<typename MqttClient>
  ReceiveResult on_receive(const esphome::remote_base::RawTimings &timings, MqttClient &mqtt,
                           bool learn_raw = false, bool suppress_rx = false) {
    if (suppress_rx)
      return ReceiveResult::SUPPRESSED;
    if (!this->valid_configuration_())
      return ReceiveResult::INVALID_CONFIGURATION;
    if (!mqtt.is_connected())
      return ReceiveResult::OFFLINE;

    esphome::remote_base::RemoteReceiveData input(
        timings, this->tolerance_percent_, esphome::remote_base::TOLERANCE_MODE_PERCENTAGE);
    for (uint8_t protocol = 1; protocol <= 8; protocol++) {
      input.reset();
      uint64_t value = 0;
      uint8_t bits = 0;
      if (!esphome::remote_base::RC_SWITCH_PROTOCOLS[protocol].decode(input, &value, &bits))
        continue;

      // Match stock on_rc_switch/dump behavior: the first matching protocol
      // wins. Keep the decoder's exact bit count, including leading zeroes.
      if (bits < 3 || bits > 64)
        continue;
      char binary[65];
      for (uint8_t i = 0; i < bits; i++)
        binary[i] = (value & (uint64_t{1} << (bits - i - 1))) ? '1' : '0';
      binary[bits] = '\0';

      this->begin_payload_("rc_switch", (esphome::millis)());
      this->append_(",\"protocol\":%u,\"bits\":%u,\"code\":\"%s\",\"value\":\"%" PRIu64 "\"}",
                    static_cast<unsigned>(protocol), static_cast<unsigned>(bits), binary, value);
      return this->publish_(mqtt, this->decoded_topic_, ReceiveResult::DECODED_PUBLISHED);
    }

    if (!learn_raw)
      return ReceiveResult::UNDECODED;
    // Reject whole captures outside the bounds. Never publish a silently
    // truncated waveform that could later be mistaken for a replayable frame.
    if (timings.empty() || timings.size() > MAX_RAW_PULSES)
      return ReceiveResult::RAW_OUT_OF_BOUNDS;
    for (int32_t duration : timings) {
      if (duration == 0 || duration < -MAX_RAW_DURATION_US || duration > MAX_RAW_DURATION_US)
        return ReceiveResult::RAW_OUT_OF_BOUNDS;
    }

    const uint32_t now = (esphome::millis)();
    if (this->raw_attempted_ && static_cast<uint32_t>(now - this->last_raw_attempt_ms_) < RAW_INTERVAL_MS)
      return ReceiveResult::RAW_RATE_LIMITED;
    this->raw_attempted_ = true;
    this->last_raw_attempt_ms_ = now;

    this->begin_payload_("raw", now);
    this->append_(",\"pulse_count\":%u,\"durations_us\":[", static_cast<unsigned>(timings.size()));
    for (size_t i = 0; i < timings.size(); i++)
      this->append_("%s%" PRId32, i == 0 ? "" : ",", timings[i]);
    this->append_("]}");
    return this->publish_(mqtt, this->raw_topic_, ReceiveResult::RAW_PUBLISHED);
  }

 private:
  bool valid_configuration_() const {
    if (this->source_ == nullptr || this->decoded_topic_ == nullptr || this->raw_topic_ == nullptr ||
        this->decoded_topic_[0] == '\0' || this->raw_topic_[0] == '\0' || this->tolerance_percent_ > 100)
      return false;
    size_t length = 0;
    for (const char *c = this->source_; *c != '\0'; c++) {
      if (++length > 32 || !((*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z') ||
                             (*c >= '0' && *c <= '9') || *c == '_' || *c == '-'))
        return false;
    }
    return length != 0;
  }

  void begin_payload_(const char *format, uint32_t now) {
    if (!this->boot_initialized_) {
      // Diagnostic correlation ID only, not a cryptographic identity. Generate
      // in the main-loop receive callback, not during global construction.
      this->boot_high_ = esphome::random_uint32();
      this->boot_low_ = esphome::random_uint32();
      this->boot_initialized_ = true;
    }
    if (++this->sequence_ == 0) {
      this->boot_high_ = esphome::random_uint32();
      this->boot_low_ = esphome::random_uint32();
      this->sequence_ = 1;
    }
    this->used_ = 0;
    this->overflow_ = false;
    this->append_("{\"schema\":1,\"source\":\"%s\",\"origin\":\"radio\",\"format\":\"%s\","
                  "\"frequency_mhz\":433.92,\"boot_id\":\"%08" PRIx32 "%08" PRIx32 "\","
                  "\"sequence\":%" PRIu32 ",\"event_id\":\"%s:%08" PRIx32 "%08" PRIx32 ":%" PRIu32 "\","
                  "\"uptime_ms\":%" PRIu32,
                  this->source_, format, this->boot_high_, this->boot_low_, this->sequence_, this->source_,
                  this->boot_high_, this->boot_low_, this->sequence_, now);
  }

  void append_(const char *format, ...) {
    if (this->overflow_)
      return;
    va_list args;
    va_start(args, format);
    const int written = std::vsnprintf(this->payload_ + this->used_, sizeof(this->payload_) - this->used_,
                                       format, args);
    va_end(args);
    if (written < 0 || static_cast<size_t>(written) >= sizeof(this->payload_) - this->used_) {
      this->overflow_ = true;
      return;
    }
    this->used_ += static_cast<size_t>(written);
  }

  template<typename MqttClient>
  ReceiveResult publish_(MqttClient &mqtt, const char *topic, ReceiveResult success) {
    if (this->overflow_)
      return ReceiveResult::PAYLOAD_TOO_LARGE;
    // Explicit event semantics: QoS 0, no retain. MQTTClientComponent returns
    // false offline; this helper never stores/replays old receive events.
    return mqtt.publish(topic, this->payload_, this->used_, 0, false) ? success : ReceiveResult::PUBLISH_FAILED;
  }

  const char *source_;
  const char *decoded_topic_;
  const char *raw_topic_;
  uint32_t tolerance_percent_;
  uint32_t sequence_{0};
  uint32_t boot_high_{0};
  uint32_t boot_low_{0};
  uint32_t last_raw_attempt_ms_{0};
  size_t used_{0};
  bool boot_initialized_{false};
  bool raw_attempted_{false};
  bool overflow_{false};
  // Keep the bounded scratch buffer off the small ESP8266 callback stack.
  // Define Receiver once (global/static), rather than constructing per frame.
  char payload_[MAX_PAYLOAD_BYTES]{};
};

}  // namespace rf_bridge
