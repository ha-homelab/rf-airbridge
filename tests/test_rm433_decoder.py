"""Exercise the real short-pulse decoder, including malformed/noisy captures."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
#include "rm433_protocol.h"
#include <iostream>
#include <vector>
int main() {
  std::vector<int32_t> timings;
  int32_t value;
  while (std::cin >> value) timings.push_back(value);
  uint32_t code = 0xabcdef, pulse = 123;
  bool valid = rf_bridge::decode_rm433_24(timings, code, pulse);
  std::cout << valid << ' ' << code << ' ' << pulse << '\n';
}
"""


def frame(code=0x5A35C9, short=240, long=720):
    values = []
    for bit in f"{code:024b}":
        values.extend((long, -short) if bit == "1" else (short, -long))
    return values + [short, -4000]


class RM433DecoderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("c++")
        if not compiler:
            raise unittest.SkipTest("C++17 compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="rm433-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "decode.cpp"
        source.write_text(HARNESS)
        cls.binary = Path(cls.temp.name) / "decode"
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT / "include"), str(source), "-o", str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def decode(self, values):
        r = subprocess.run([str(self.binary)], input=" ".join(map(str, values)),
                           check=True, capture_output=True, text=True)
        return tuple(map(int, r.stdout.split()))

    def assert_rejected(self, values):
        # Failure must not leak a partial code into the caller's output.
        self.assertEqual(self.decode(values), (0, 0xABCDEF, 123))

    def test_full_24_bit_range_and_leading_zeroes(self):
        for code in (0, 5, 0x5A35C9, 0xFFFFFF):
            self.assertEqual(self.decode(frame(code)), (1, code, 240))

    def test_realistic_pulse_jitter_and_long_sync(self):
        values = frame()
        for index in range(48):
            values[index] += (-19, 7, 25, -11)[index % 4]
        values[-1] = -7500
        valid, code, pulse = self.decode(values)
        self.assertEqual((valid, code), (1, 0x5A35C9))
        self.assertTrue(220 <= pulse <= 260)

    def test_reject_truncation_extra_bits_and_noise_prefix(self):
        for values in ([], frame()[:-2], frame()[:-1], frame() + [240, -720],
                       [100, -100] + frame(), frame()[:20]):
            self.assert_rejected(values)

    def test_reject_corruption_at_every_bit(self):
        for index in range(48):
            for bad in (0, 2**31 - 1, -(2**31)):
                values = frame()
                values[index] = bad
                self.assert_rejected(values)

    def test_reject_bad_sync_and_other_timings(self):
        for tail in ([240, -1000], [0, -4000], [-240, -4000], [240, -120001]):
            self.assert_rejected(frame()[:-2] + tail)
        self.assert_rejected(frame(short=400, long=1200))
        self.assert_rejected(frame(short=350, long=1050))
        self.assert_rejected(frame(short=240, long=240))


if __name__ == "__main__":
    unittest.main()
