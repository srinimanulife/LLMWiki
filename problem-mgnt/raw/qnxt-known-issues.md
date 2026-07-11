# QNXT — Known Issues & Problem Records

**Product:** QNXT (TriZetto/Cognizant)
**Domain:** Claims Administration, Eligibility, Provider Management, Authorizations
**Role in TriZetto Suite:** Primary claims source system — adjudicates managed care claims, handles COB (Coordination of Benefits), manages referral/authorization workflows, and posts capitation. Integrates downstream with EDM, EAM, TCS, NetworX, and FRM. Facets is the parallel claims system handling commercial/Medicare; QNXT handles Medicaid/managed care.

---

## Claims Processing Engine

### PRB-QNXT-001 — Overnight Batch Fails on ANSI 837P Claims with Missing Rendering Provider NPI
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** 6.2.x - 6.4.x
- **Summary:** Overnight claims adjudication batch fails on ANSI X12 837P claims with missing rendering provider NPI.
- **Root Cause:** `ClaimBatch.processANSI()` throws `NullReferenceException` when loop 2310B (rendering provider) is absent; no graceful fallback.
- **Resolution:** Added null-safe provider lookup with fallback to billing NPI; added validation rule PRV-NULL-001.
- **Category:** Batch Processing
- **Cross-system Comparison with Facets:** Both QNXT PRB-QNXT-001 and Facets PRB-FAC-001 are P1 recurring overnight batch failures triggered by missing/null values in claim data. Facets fails on `supplemental_coverage_code`; QNXT fails on rendering provider NPI (loop 2310B). Both required null guards as the fix. QNXT's failure surface is the ANSI X12 transaction level; Facets' failure is at the coverage code level. Neither system had input validation gates before the batch processor.

### PRB-QNXT-002 — Duplicate Claim Detection False Positives Across Billing Cycles
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 6.1.x - 6.4.x
- **Summary:** Duplicate claim detection fires on identical claims submitted across different billing cycles.
- **Root Cause:** `DuplicateFilter` uses `service_date + billed_amount` only; ignores `billing_cycle_id` in comparison key.
- **Resolution:** Extended duplicate key to include `billing_cycle_id`; false-positive rate reduced from 8% to <0.2%.
- **Category:** Business Logic
- **Cross-system Comparison with Facets:** Facets PRB-FAC-005 has the same category (Business Logic) — duplicate detection ignores `claim_type=CORRECTED`. QNXT ignores `billing_cycle_id`; Facets ignores claim type. Both represent incomplete duplicate comparison keys. The root cause pattern — narrow comparison key definition — is shared. Recommended: cross-system duplicate key audit.

---

## Eligibility & Benefits Engine

### PRB-QNXT-003 — COB Calculation Incorrect After Mid-Year Payer Order Change
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 6.3.x
- **Summary:** COB (Coordination of Benefits) calculation produces incorrect patient liability when secondary payer order changes mid-year.
- **Root Cause:** `COBCalculator` caches `payer_order` at session start; mid-year COB changes not refreshed until cache TTL expires (24h).
- **Resolution:** Cache TTL reduced to 1h for COB records; added real-time invalidation on `payer_order` change event.
- **Category:** Cache/Sync
- **Cross-system Comparison with Facets:** Facets PRB-FAC-007 is a parallel cache/sync issue in Authorization Management (4h TTL for emergency PAs). Both are cache invalidation failures. QNXT's 24h COB cache causes financial liability errors; Facets' 4h auth cache causes care coordination delays. Pattern: both systems over-rely on long TTL caches without event-driven invalidation.

### PRB-QNXT-004 — Mass Eligibility Termination Silently Skips Members >10,000
- **Severity:** P1 | **Recurrence:** First Occurrence | **Version:** 6.4.0
- **Summary:** Mass eligibility termination job silently skips members when group enrollment exceeds 10,000 records.
- **Root Cause:** Batch job uses fixed-size `ArrayList(10000)`; overflow throws `IndexOutOfRangeException` caught and swallowed.
- **Resolution:** Switched to streaming `IEnumerable` with chunked DB commits; added reconciliation count check post-job.
- **Category:** Data Loss
- **Cross-system Comparison with Facets:** Facets PRB-FAC-006 is a direct parallel — fixed-size buffer (500 records) in HIPAA 834 enrollment parser silently truncates overflow. Both are P1 data loss issues caused by fixed-capacity buffers. QNXT threshold is 10,000; Facets threshold is 500. Resolution pattern is identical: streaming parser + reconciliation count. Demonstrates systemic fixed-buffer anti-pattern across both claim source systems.

---

## Provider & Network Management

### PRB-QNXT-005 — CAQH ProView Import Fails for Multi-Location Providers
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 6.2.x - 6.4.x
- **Summary:** Provider panel update from CAQH ProView fails when provider has multiple practice locations.
- **Root Cause:** CAQH import maps only first address record; subsequent locations overwrite rather than append.
- **Resolution:** Fixed import to merge location list; added deduplication by `address_hash` before persist.
- **Category:** Integration
- **Cross-system Comparison with Facets:** Facets PRB-FAC-003 — NPI registry unreachable causes silent credentialing failure. Both affect provider data quality. QNXT failure is data mapping (overwrite vs append); Facets failure is resilience (no retry on external registry call). Combined effect: provider data incomplete in both systems simultaneously when either fails.

---

## Referral & Authorization Module

### PRB-QNXT-006 — Urgent Care Authorizations Stuck in Pending After 72h Timeout
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 6.3.x - 6.4.x
- **Summary:** Urgent care authorizations remain in pending status after 72h timeout; downstream claims denied.
- **Root Cause:** `AuthorizationTimeoutJob` checks `created_at` instead of `requested_at`; urgent care SLA clock starts at wrong timestamp.
- **Resolution:** Fixed timestamp reference to use `requested_at`; added SLA escalation alert at 48h mark.
- **Category:** Workflow
- **Cross-system Comparison with Facets/EAM:** Facets PRB-FAC-007 causes emergency PA approvals to be stale (cache lag). QNXT PRB-QNXT-006 causes urgent care PAs to be stuck in pending (wrong SLA clock). EAM PRB-EAM-004 causes weekend SLA breaches to go unescalated. All three represent authorization timeliness failures across different system layers (cache, workflow, scheduling).

---

## Financial & Capitation Module

### PRB-QNXT-007 — Capitation Export Contains Duplicate Rows for Multi-Plan Members
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** All versions
- **Summary:** Monthly capitation file export contains duplicate member rows for members enrolled in multiple sub-plans.
- **Root Cause:** Capitation export query joins `member_plan` without `DISTINCT` on `member_id`; multi-plan members appear N times.
- **Resolution:** Added `DISTINCT member_id` with `MAX(effective_date)` aggregation; capitation accuracy improved from 94% to 99.8%.
- **Category:** Data Integrity
- **Cross-system Impact:** Duplicate capitation rows in QNXT export flow into FRM reconciliation. FRM PRB-FRM-001 (race condition between Facets and QNXT capitation postings) and PRB-FRM-002 (retroactive adjustment mismatches) are downstream effects of upstream capitation data quality issues in both claim source systems.

---

## Reporting & Analytics

### PRB-QNXT-008 — HEDIS MLR-2 Medication Adherence Denominator Under-Counts 90-Day Fills
- **Severity:** P3 | **Recurrence:** First Occurrence | **Version:** 6.4.0 - 6.4.1
- **Summary:** HEDIS measure MLR-2 (Medication Adherence) denominator under-counts members on 90-day supply fills.
- **Root Cause:** 90-day supply fills counted as single fill event; PDC denominator calculation uses `fill_count` not `days_supply`.
- **Resolution:** Rewritten PDC calculation using `days_supply / observation_period`; MLR-2 rate increased 3.2 percentage points.
- **Category:** Reporting
- **Cross-system Comparison with Facets:** Facets PRB-FAC-008 (HEDIS denominator over-counted due to missing LOB filter) and QNXT PRB-QNXT-008 (HEDIS denominator under-counted due to wrong PDC calculation) represent opposite HEDIS reporting errors in the two claim source systems. Facets inflates denominators; QNXT deflates them. Both affect NCQA measure submission accuracy. A cross-system HEDIS data reconciliation step is recommended before CMS/NCQA submission.

---

## Summary: QNXT Issue Patterns vs Facets

| Category | QNXT | Facets | Common Pattern |
|---|---|---|---|
| Batch Processing | PRB-QNXT-001 | PRB-FAC-001 | Null/missing-value crashes in overnight batch |
| Data Loss | PRB-QNXT-004 | PRB-FAC-006 | Fixed-size buffer overflow, silent truncation |
| Business Logic | PRB-QNXT-002 | PRB-FAC-005 | Incomplete duplicate detection key |
| Cache/Sync | PRB-QNXT-003 | PRB-FAC-007 | Long-TTL cache without event invalidation |
| Integration | PRB-QNXT-005 | PRB-FAC-003 | External registry resilience/mapping gaps |
| Reporting (HEDIS) | PRB-QNXT-008 | PRB-FAC-008 | HEDIS denominator errors (under vs over) |

**Recurring Issues:** PRB-QNXT-001, PRB-QNXT-002, PRB-QNXT-003, PRB-QNXT-005, PRB-QNXT-006, PRB-QNXT-007
**P1 Issues:** PRB-QNXT-001, PRB-QNXT-004
