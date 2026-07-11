# Facets — Known Issues & Problem Records

**Product:** Facets (TriZetto/Cognizant)
**Domain:** Claims Administration, Member Management, Provider Network
**Role in TriZetto Suite:** Primary claims source system — adjudicates commercial and government claims, manages member enrollment, eligibility, and premium billing. Integrates downstream with EDM, EAM, TCS, NetworX, and FRM.

---

## Claims Adjudication Engine

### PRB-FAC-001 — Batch Processing Failure: Null Pointer on Medicare Supplemental Claims
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** 19.2.x
- **Summary:** Claims batch processing fails with null pointer exception on Medicare supplemental claims.
- **Root Cause:** Missing null check in `ClaimAdjudicator.processBatch()` when `supplemental_coverage_code` is absent.
- **Resolution:** Added null guard in `processBatch()` and fallback to default coverage code; patched in Facets 19.2.3.
- **Category:** Batch Processing
- **Cross-system Impact:** Batch failures in Facets Claims Adjudication Engine delay downstream EDM encounter submission and FRM reconciliation windows. Similar batch null-pointer patterns observed in QNXT Claims Processing Engine (PRB-QNXT-001).

### PRB-FAC-005 — Duplicate Claim Detection Incorrectly Flags Corrected Claims
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 18.x - 19.x
- **Summary:** Duplicate claim detection incorrectly flags resubmitted corrected claims as duplicates.
- **Root Cause:** `DuplicateClaimChecker` compares `claim_id` without considering `claim_type=CORRECTED` flag.
- **Resolution:** Added `claim_type` to duplicate detection logic; CORRECTED claims bypass exact-match check and use fuzzy date window.
- **Category:** Business Logic
- **Cross-system Impact:** QNXT has a parallel issue (PRB-QNXT-002) where duplicate detection ignores `billing_cycle_id`. Both systems share a conceptual gap in multi-attribute duplicate key design.

---

## Eligibility Verification Service

### PRB-FAC-002 — Eligibility Lookup Timeout for Dual-Eligible Members
- **Severity:** P2 | **Recurrence:** First Occurrence | **Version:** 19.1.x
- **Summary:** Member eligibility lookup times out for dual-eligible members with multiple plan records.
- **Root Cause:** Database query in `EligibilityService.getMemberPlan()` performs full table scan when member has >3 active plans.
- **Resolution:** Added composite index on `(member_id + plan_status + effective_date)`; query time reduced from 45s to 0.3s.
- **Category:** Performance
- **Cross-system Impact:** Facets Eligibility Verification Service timeout patterns differ from QNXT Eligibility & Benefits Engine (PRB-QNXT-003, PRB-QNXT-004). Facets timeout is query-plan driven; QNXT failures are cache staleness (COB) and buffer overflow (mass termination). Both affect dual-eligible member handling.

---

## Provider Network Management

### PRB-FAC-003 — Provider Credentialing Silent Failure on NPI Registry Unreachable
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 18.4.x - 19.2.x
- **Summary:** Provider credentialing update fails silently when NPI registry is unreachable.
- **Root Cause:** `ProviderCredentialJob` swallows `IOException` without retry or alerting; NPI calls not idempotent.
- **Resolution:** Implemented exponential backoff retry (3 attempts) and SNS alert on final failure; added dead-letter queue.
- **Category:** Integration
- **Cross-system Impact:** QNXT Provider & Network Management (PRB-QNXT-005) has a parallel integration failure with CAQH ProView for multi-location providers. Both systems rely on external NPI/CAQH registries; resilience patterns (retry, DLQ) should be standardized across Facets and QNXT.

---

## Member Enrollment

### PRB-FAC-006 — HIPAA 834 File Drops Records for Groups >500 Members
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** 19.0.x - 19.2.x
- **Summary:** HIPAA 834 enrollment file processing drops records when group_size exceeds 500 members.
- **Root Cause:** `FileParser` uses fixed-size buffer (500 records); overflow silently truncates remaining enrollees.
- **Resolution:** Switched to streaming parser with dynamic buffer; added record-count reconciliation step post-load.
- **Category:** Data Loss
- **Cross-system Impact:** Enrollment data loss in Facets affects downstream EDM HCC RAF scoring (PRB-EDM-003) because disenrolled/unenrolled members are missing from risk adjustment pool. Also impacts FRM premium reconciliation accuracy.

---

## Authorization Management

### PRB-FAC-007 — Prior Auth Approvals Not Real-Time for Emergency Procedures
- **Severity:** P2 | **Recurrence:** First Occurrence | **Version:** 19.2.0
- **Summary:** Prior authorization approvals not reflected in real-time for emergency procedures.
- **Root Cause:** `AuthCache` TTL set to 4 hours; emergency PA updates not triggering cache invalidation event.
- **Resolution:** Reduced `AuthCache` TTL to 15 minutes for emergency PA types; added cache-bust on PA status change event.
- **Category:** Cache/Sync
- **Cross-system Impact:** Facets Authorization Management and EAM (Enterprise Authorization Management) share authorization state. EAM retrospective approval propagation failure (PRB-EAM-002) is a related cross-system issue where Facets and QNXT downstream systems miss EAM approval events entirely.

---

## Premium Billing Module

### PRB-FAC-004 — Incorrect Premium Calculation at Age-Boundary Crossing
- **Severity:** P1 | **Recurrence:** First Occurrence | **Version:** 19.2.1
- **Summary:** Incorrect premium calculation for family plans when dependent ages cross billing cycle boundary.
- **Root Cause:** Age calculation in `PremiumCalculator` uses enrollment date instead of billing period start date.
- **Resolution:** Fixed date reference in `age_at_billing_date()`; regression test suite expanded to cover age-boundary cases.
- **Category:** Data Integrity
- **Cross-system Impact:** Premium miscalculations in Facets flow into FRM financial reconciliation. FRM retroactive adjustment issue (PRB-FRM-002) is exacerbated when Facets posts premium corrections across billing periods.

---

## Financial Reconciliation Manager (FRM — Facets Module)

### PRB-FAC-009 — Capitation Payment Mismatch on Special Characters in plan_id
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 19.1.x - 19.2.x
- **Summary:** Daily reconciliation run mismatches capitation payments when `plan_id` contains special characters.
- **Root Cause:** SQL parameterization strips special chars from `plan_id` before comparison; causes phantom mismatches.
- **Resolution:** Switched to prepared statement with explicit VARCHAR cast; mismatch rate dropped from 2.3% to 0%.
- **Category:** Data Integrity

### PRB-FAC-010 — End-of-Month FRM Batch Deadlock with EDM Parallel Postings
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** 19.2.x
- **Summary:** End-of-month FRM batch deadlocks when EDM encounters parallel capitation and encounter postings.
- **Root Cause:** FRM acquires table-level lock on `fin_transactions`; EDM posting job attempts row-level lock on same table simultaneously.
- **Resolution:** Serialized FRM batch window to off-peak (2-3 AM); added deadlock retry with exponential backoff.
- **Category:** Batch Processing

---

## Reporting & Analytics

### PRB-FAC-008 — HEDIS Reports Show Inflated Denominator Counts
- **Severity:** P3 | **Recurrence:** Recurring | **Version:** All versions
- **Summary:** Monthly HEDIS measure reports show inflated denominator counts for preventive care measures.
- **Root Cause:** HEDIS query joins on `member_id` without filtering by LOB; commercial and Medicaid members double-counted.
- **Resolution:** Added LOB filter to all HEDIS denominator queries; added data quality check step before report generation.
- **Category:** Reporting
- **Cross-system Impact:** QNXT Reporting & Analytics has a parallel HEDIS issue (PRB-QNXT-008) where MLR-2 Medication Adherence denominator under-counts 90-day fills. Facets inflates denominators; QNXT under-counts them. Both affect HEDIS measure accuracy and NCQA submission quality.

---

## Summary: Facets Issue Patterns

| Category | Count | Notes |
|---|---|---|
| Batch Processing | 3 | PRB-FAC-001, PRB-FAC-010 (FRM), TCS-005 |
| Data Integrity | 3 | PRB-FAC-004, PRB-FAC-009, PRB-FAC-002 |
| Business Logic | 1 | PRB-FAC-005 |
| Integration | 1 | PRB-FAC-003 |
| Data Loss | 1 | PRB-FAC-006 |
| Cache/Sync | 1 | PRB-FAC-007 |
| Reporting | 1 | PRB-FAC-008 |

**Recurring Issues:** PRB-FAC-001, PRB-FAC-003, PRB-FAC-005, PRB-FAC-006, PRB-FAC-008, PRB-FAC-009, PRB-FAC-010
**P1 Issues:** PRB-FAC-001, PRB-FAC-004, PRB-FAC-006, PRB-FAC-010
