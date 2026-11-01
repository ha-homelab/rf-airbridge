#!/usr/bin/env bash
set -euo pipefail

seconds="${1:-60}"
if [[ $# -gt 1 || ! "$seconds" =~ ^[0-9]{1,4}$ ]]; then
  echo "Usage: bash fuzz/run.sh [seconds per target: 1-3600]" >&2
  exit 2
fi
seconds=$((10#$seconds))
if (( seconds < 1 || seconds > 3600 )); then
  echo "Fuzz duration must be between 1 and 3600 seconds" >&2
  exit 2
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/rf-airbridge-fuzz.XXXXXX")"
cleanup() {
  status=$?
  if (( status == 0 )); then
    rm -rf -- "$work"
  else
    echo "Fuzzing failed; binaries, corpus and crash inputs retained in: $work" >&2
  fi
}
trap cleanup EXIT

for target in decoder transmit; do
  "${CXX:-clang++}" -std=c++17 -Wall -Wextra -Werror -O1 -g \
    -fsanitize=fuzzer,address,undefined -fno-sanitize-recover=all \
    -fno-omit-frame-pointer -I"$root/include" \
    "$root/fuzz/$target.cpp" -o "$work/$target"
  mkdir "$work/corpus-$target"
  cp "$root/fuzz/corpus/$target/"* "$work/corpus-$target/"
  "$work/$target" -seed=1 -max_total_time="$seconds" -max_len=4096 \
    -timeout=5 -rss_limit_mb=512 -artifact_prefix="$work/" "$work/corpus-$target"
done
