#!/usr/bin/env python3
"""Validate/compile the example with dummy credentials, never contact a node."""

import argparse
import base64
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--with-wake-on-lan", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="rf-airbridge-validate-") as directory:
        staging = Path(directory)
        for name in ("components", "include", "packages"):
            shutil.copytree(root / name, staging / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(root / "device.example.yaml", staging / "device.yaml")
        if args.with_wake_on_lan:
            example = (staging / "device.yaml").read_text()
            if example.count("\npackages:\n") != 1:
                raise ValueError("Expected exactly one example packages map")
            (staging / "device.yaml").write_text(example.replace(
                "\npackages:\n",
                "\npackages:\n  living_tv_wake: !include packages/wake-on-lan.yaml\n",
                1,
            ))
        secrets = {
            "wifi_ssid": "RF-AIRBRIDGE-VALIDATION-ONLY",
            "wifi_password": "not-a-real-password",
            "api_encryption_key": base64.b64encode(bytes(32)).decode(),
            "ota_password": "not-a-real-ota-password",
            "mqtt_broker": "mqtt.example.invalid",
            "mqtt_username": "validation",
            "mqtt_password": "not-a-real-mqtt-password",
            "living_tv_mac_address": "02:00:00:00:00:01",
        }
        (staging / "secrets.yaml").write_text(yaml.safe_dump(secrets))
        action = "config" if args.config_only else "compile"
        return subprocess.run([sys.executable, "-m", "esphome", action, str(staging / "device.yaml")]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
