# Contributing

Use [GitHub issues](https://github.com/ha-homelab/rf-airbridge/issues) for non-sensitive bug reports, questions and
feature proposals. Include the exact version/commit, environment, expected and
actual behavior, and a minimal sanitized reproduction. Check existing issues
first and keep follow-up evidence in the original thread. For vulnerabilities,
use the [private security process](SECURITY.md).

Submit a focused pull request against `main`. Describe the user-visible problem,
the resulting behavior, compatibility implications and checks performed. Preserve
existing authorship and third-party license/provenance records. Discuss changes
to protocols, storage, device safety or dependency/runtime requirements before
making an incompatible change. English is the common language for code review
and project documentation.

## Development and validation

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes --only-binary=:all: -r requirements-test.txt -r requirements-capture.txt
python -m unittest discover -s tests -v
```

Firmware CI compiles the example against ESPHome 2026.8.2 using dummy credentials. Host C++ tests require a C++ compiler. Compilation does not establish radio compliance or safe operation of a physical load.

The [CI workflow](.github/workflows/tests.yml) is the authoritative list of required jobs.
Use isolated test data and temporary outputs. Never run a device write, unlock,
deployment or publication command merely to validate a documentation change.

## Test and review policy

Changes to behavior must add or update automated tests that fail for the old
defect and cover the new boundary; regression fixes should include the relevant
failure case. If automation is infeasible, explain why in the PR and document
the reproducible manual procedure and limits. Update user/API documentation and
release notes for user-visible changes. Keep compiler, lint, static-analysis and
test assertions enabled, resolve new warnings, and document any remaining
warning with its reason and scope. Do not suppress a real security finding to
obtain a passing check. Wait for required checks and independent review before
merging; do not use an administrator bypass.

The native receiver and transmitter harnesses support AddressSanitizer and
UndefinedBehaviorSanitizer with GCC/Clang:

```bash
RF_CPP_SANITIZERS=1 python -m unittest discover -s tests -v
```

Host CI enables both sanitizers and retains C++ assertions. It exercises the
actual receiver patch, bridge serialization and transmit validator with hardware
doubles; it does not instrument a running ESP8266 or prove radio behavior.

## Reproducible Python dependencies

The `.in` files declare direct dependencies. The corresponding `.txt` files pin
all resolved dependencies and approved archive SHA-256 hashes across supported
platforms. Install with `--require-hashes`; do not remove this check to work around
a missing archive. Review dependency updates and regenerate the locks with:

```sh
uv pip compile requirements-test.in --generate-hashes --universal --python-version 3.12 --output-file requirements-test.txt
uv pip compile requirements-capture.in --generate-hashes --universal --python-version 3.12 --output-file requirements-capture.txt
```

Run the documented tests in a fresh virtual environment after updating a lock.

## Source releases

Use immutable Semantic Versioning tags (`vMAJOR.MINOR.PATCH`) for source snapshots.
The first source release is `v0.1.0`; do not move an existing release tag.
These versions identify this repository’s source, configuration examples, tests and documentation. They are independent of the required ESPHome version and do not provide a precompiled firmware image. Compile for the documented board and validate the installation before operating a physical load.

Before tagging, identify the exact reviewed commit and verify its required CI
checks. Each release must link that commit and describe changes, upgrade
implications and security impact, including known limits. GitHub source archives
allow users to obtain the exact tagged tree; preserve all bundled licenses and
upstream notices. Report defects against the source tag or full commit ID.
