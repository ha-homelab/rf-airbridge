# OpenSSF Passing evidence

This is a source-backed work record for the [OpenSSF Best Practices Passing
criteria](https://www.bestpractices.dev/en/criteria/0). It does not assert that a
badge has been awarded. The partial [machine-readable assessment](../.bestpractices.json)
leaves unverified criteria unknown.

## Available evidence

- Purpose, installation and operating limitations: [README](../README.md).
- Public Git source, commit history and change proposals: [ha-homelab/rf-airbridge](https://github.com/ha-homelab/rf-airbridge).
- Bug reports and retained discussion: [issues](https://github.com/ha-homelab/rf-airbridge/issues).
- Contribution requirements, test policy and test invocation: [CONTRIBUTING](../CONTRIBUTING.md).
- Private reporting process and response policy: [SECURITY](../SECURITY.md).
- Trust boundaries, source references and negative-test evidence: [security design](security-design.md).
- Build/test automation: [workflow](../.github/workflows/tests.yml) and [actual run results](https://github.com/ha-homelab/rf-airbridge/actions).
- Project license: [MIT](../LICENSE); third-party terms still apply.

## Initial scanner inventory — 2026-10-08

The authenticated GitHub inventory found 8 open code-scanning alerts
(including Scorecard policy findings) and 0 open Dependabot alerts.
This is a dated baseline, not a statement about the post-merge state. A scanner
configuration error or disabled scanner must not be recorded as zero findings.
Check [Code scanning](https://github.com/ha-homelab/rf-airbridge/security/code-scanning) and
[Dependabot](https://github.com/ha-homelab/rf-airbridge/security/dependabot) after the changed default branch is
analyzed.

## Unresolved criteria and applicability

The existing native receiver, serialization and TX-validation harnesses run under AddressSanitizer and UndefinedBehaviorSanitizer in host CI, with C++ assertions enabled. All 24 host tests also passed locally with sanitizers on 2026-10-08. This covers the exercised host paths with hardware doubles; it does not instrument a live ESP8266 or certify RF behavior. RF replay and third-party ESPHome transport policies need an explicit applicability assessment for cryptography criteria.

The project maintainer must confirm secure-design/common-error knowledge for
this project and supply the history of bug, enhancement and vulnerability
reports across all channels. Confirm actual private-reporting availability and
review/branch settings. Verify releases have meaningful change/security notes;
measure test coverage and map static/dynamic analysis to every project-owned
language. Review each cryptographic criterion individually. Do not transfer
another repository's attestations, badge identifier or test results here.

Record each completed analysis with its source SHA, commands/tool versions,
result and material limitations. Add the repository's actual badge only after
its own public assessment is saved and verified.
