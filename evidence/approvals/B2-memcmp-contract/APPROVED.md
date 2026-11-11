# Approval: B2, memcmp's boundary contract with its bundled changes (Zach, relaying the auditor, 2026-11-11)

Zach's answer, verbatim:

> Auditor: B2 OK to land as patch.diff stands at wip/b2-memcmp ab697bd, delta included. Verified: patch == branch diff, delta == 0c1581f..edd3b62; lock PASS 58, scan PASS, -k b2 13/13, -k campaign 9/9, selftest 110/110 (with the three --tools guards); tools-probe.txt shows exactly the nine tools on start and resume. F-002's sandboxed run matches the auditor's native one. Agreed: C-17's round-4 Codex reviewer judges F-002.

Applied: `patch.diff` exactly as written (the staged change was compared byte for byte), with its proof.lock. That proof.lock also repairs main's, which lacked T-006's 19 test fixtures. After the land, the daemon is restarted onto the new campaign.py (T-008).
