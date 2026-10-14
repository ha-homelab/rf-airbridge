# Quality and assessment scope

This assessment covers the original RF extension, configuration examples, capture tools and bundled receiver code. It does not award a badge to
upstream Home Assistant, firmware, hosted platforms or downstream installations.

## Verification

Use the commands in [CONTRIBUTING](../CONTRIBUTING.md) and the current GitHub
Actions workflows. Keep the source commit, tool versions, command and outcome
with any evidence. A green job describes the checks it actually executed; a
path-filtered skipped job is not a fresh execution of those checks.

Compiler/safe-language warnings, static security analysis and dynamic tests have
different scopes. Document individual accepted warnings rather than disabling
rules globally. A successful simulated test or compilation does not establish
physical device behavior.

## Security argument

RF is unauthenticated and replayable. MQTT and ESPHome API deployment credentials belong in private configuration. Native buffers and pulse counts are bounded; host ASan/UBSan checks exercise the runtime with hardware doubles.

The security policy and implementation-specific tests describe the controls
for those boundaries. This is a compact engineering argument, not an independent
security certification or a completed formal assurance case.

## Current limits

Whole-project statement coverage of at least 80% has not been established by
this assessment. Test counts are not a coverage percentage. The maintainer has
confirmed knowledge of secure design and common vulnerability classes; knowledge
does not replace the implementation evidence. Governance records the absence of
a tested backup-maintainer/recovery arrangement, so Silver continuity is unmet.

Only a saved and verified public OpenSSF assessment establishes an awarded badge.
Missing evidence stays unmet until it is actually produced.

## Assessment record — 2026-10-14

The current GitHub inventory found no non-PR issues, public project advisories
or open dependency alerts. Pull requests came from the maintainer and maintenance
bots. The maintainer confirmed no outside-GitHub bug, enhancement or vulnerability
reports in the preceding 12 months. Private vulnerability reporting is enabled.
Gitleaks scanned 21 available Git commits without a finding. These observations
are dated evidence, not a permanent guarantee or a claim of zero future defects.

Local verification passed all 44 host tests with `RF_CPP_SANITIZERS=1`; ASan and
UBSan instrument the native harnesses and assertions remain enabled. This is
not a live-device acceptance test or a standalone fuzzing campaign.
