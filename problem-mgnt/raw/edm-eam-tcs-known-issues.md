# EDM, EAM, and TCS — Known Issues & Problem Records

## EDM — Encounter Data Management

**Product:** EDM (TriZetto/Cognizant Encounter Data Management)
**Domain:** CMS Encounter Submission, Risk Adjustment, RADV Compliance
**Role in TriZetto Suite:** Receives processed encounters from Facets and QNXT; submits to CMS for risk adjustment. Manages HCC (Hierarchical Condition Category) RAF scores. Feeds into FRM for reconciliation.

---

### PRB-EDM-001 — CMS Batch Submission Aborts Entire File on Single Bad DX Code
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** 5.1.x - 5.3.x
- **Summary:** EDM batch submission to CMS rejects entire file when a single encounter record has malformed DX code.
- **Root Cause:** EDM validator uses fail-fast strategy; first error aborts entire 50,000-record batch.
- **Resolution:** Switched to collect-all-errors strategy; bad records quarantined to error queue; clean records submitted.
- **Category:** Batch Processing
- **Cross-system Impact:** EDM batch failures block CMS risk adjustment submissions. Facets enrollment data loss (PRB-FAC-006) and EDM ICD-10 crosswalk errors (PRB-EDM-002) are upstream causes of bad DX records entering the EDM batch.

### PRB-EDM-002 — ICD-10 to ICD-9 Crosswalk Incorrect for Combination Diagnoses
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 5.2.x - 5.3.x
- **Summary:** ICD-10 to ICD-9 crosswalk produces incorrect codes for combination diagnoses mapped to multiple ICD-10 codes.
- **Root Cause:** Crosswalk table has 1:1 mapping; combination DX codes (e.g. E11.65) split incorrectly into two ICD-9 entries.
- **Resolution:** Updated crosswalk to flag combination codes; added manual review queue for multi-mapped entries.
- **Category:** Data Integrity

### PRB-EDM-003 — HCC RAF Score Excludes Mid-Year Disenrolled Members
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 5.3.x
- **Summary:** HCC RAF score recalculation incorrectly excludes members disenrolled mid-year from risk adjustment pool.
- **Root Cause:** Disenrollment filter excludes members with `end_date < year_end`; partial-year members should be prorated.
- **Resolution:** Fixed filter to include partial-year members; added prorated weight calculation for days enrolled.
- **Category:** Data Integrity
- **Cross-system Impact:** Facets member enrollment data loss (PRB-FAC-006) directly reduces the EDM RAF population — members never enrolled in Facets cannot appear in EDM risk adjustment. Combined effect: underreported RAF scores and reduced CMS payment accuracy.

### PRB-EDM-004 — RADV Audit Extract Misses Batch-Submitted Encounters
- **Severity:** P3 | **Recurrence:** First Occurrence | **Version:** 5.3.0
- **Summary:** RADV audit extract misses encounters submitted via batch API vs. online portal due to `source_type` filter.
- **Root Cause:** RADV query filters on `source_type = 'portal'`; batch-submitted encounters tagged `source_type = 'api'` excluded.
- **Resolution:** Removed `source_type` filter from RADV extract; added `source_type` column to audit report for transparency.
- **Category:** Reporting
- **Cross-system Impact:** FRM audit trail incompleteness (PRB-FRM-004) and EDM RADV extract incompleteness compound during CMS RADV audits — both systems independently omit records that auditors need.

### PRB-EDM-005 — Supplemental Data Ingestion OOM on Files >2GB
- **Severity:** P1 | **Recurrence:** First Occurrence | **Version:** 5.2.0
- **Summary:** Supplemental data file ingestion stalls when file size exceeds 2GB compressed.
- **Root Cause:** `SupplementalIngestor` loads entire file into memory; OOM on files >2GB compressed (8GB+ uncompressed).
- **Resolution:** Rewrote ingestor to use streaming GZIP reader with configurable chunk size (default 100MB).
- **Category:** Batch Processing

---

## EAM — Enterprise Authorization Management

**Product:** EAM (TriZetto/Cognizant Enterprise Authorization Management)
**Domain:** Prior Authorization, Clinical Decision Support, Auth Routing
**Role in TriZetto Suite:** Central authorization engine used by both Facets and QNXT. Manages PA workflows, clinical review queues, and auth propagation downstream to claims adjudication.

---

### PRB-EAM-001 — DME Requests Route to Wrong Clinical Review Queue
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 4.1.x - 4.2.x
- **Summary:** Prior authorization requests for DME (Durable Medical Equipment) route to wrong clinical review queue.
- **Root Cause:** `AuthRouter` evaluates `procedure_type` before `place_of_service`; DME with `place_of_service=12` (Home) misfires.
- **Resolution:** Added DME check as first routing condition in `AuthRouter.route()` before `procedure_type` evaluation.
- **Category:** Workflow
- **Cross-system Impact:** DME misrouting causes downstream QNXT authorization timeouts (PRB-QNXT-006) because correctly routed requests go to a different queue than where QNXT's SLA monitor polls.

### PRB-EAM-002 — Retrospective Auth Approvals Not Propagating to Facets and QNXT
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** 4.2.x
- **Summary:** Retrospective authorization approvals not propagating to downstream Facets and QNXT claims adjudication.
- **Root Cause:** EAM event publisher uses fire-and-forget HTTP POST; no acknowledgment; downstream systems miss events on timeout.
- **Resolution:** Switched to SQS-based event publishing with consumer acknowledgment and DLQ; retry count = 3.
- **Category:** Integration
- **Cross-system Impact:** This is the most critical cross-system integration failure in the TriZetto suite. EAM approves retrospective authorizations, but Facets and QNXT never receive the event — claims are denied even though authorization exists in EAM. Root fix requires both EAM (reliable event publish) and Facets/QNXT (idempotent event consume) changes.

### PRB-EAM-003 — CDS Alert Fatigue — 73% Auto-Dismissed by Reviewers
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** 4.1.x - 4.2.x
- **Summary:** CDS alert fatigue — 73% of clinical alerts auto-dismissed by reviewers within 5 seconds.
- **Root Cause:** Alert severity scores not calibrated to patient context; high-priority alerts shown for low-risk procedures.
- **Resolution:** Implemented context-aware severity scoring using `member_risk_tier` and `procedure_frequency`; alert volume reduced 41%.
- **Category:** Business Logic

### PRB-EAM-004 — Weekend Auth SLA Breaches Not Triggering Escalation Emails
- **Severity:** P3 | **Recurrence:** Recurring | **Version:** All versions
- **Summary:** Auth turnaround time SLA breaches not triggering escalation emails for weekend requests.
- **Root Cause:** SLA escalation job runs M-F only; weekend requests accumulate until Monday morning batch.
- **Resolution:** Extended SLA escalation job to 7-day schedule; added on-call pager integration for P1/P2 SLA breaches.
- **Category:** Workflow
- **Cross-system Impact:** QNXT urgent care auth SLA failures (PRB-QNXT-006) and EAM weekend escalation gaps (PRB-EAM-004) together mean urgent care requests submitted on weekends have neither SLA monitoring (QNXT) nor escalation (EAM) — maximum exposure window for care delay.

---

## TCS — TriZetto Claims Solutions

**Product:** TCS (TriZetto Claims Solutions)
**Domain:** Claims Intake, Validation, Remittance Processing, Correspondence
**Role in TriZetto Suite:** Claims intake and clearinghouse layer. Validates ANSI X12 claims before they reach Facets or QNXT. Handles 835 ERA remittance and generates member EOB correspondence.

---

### PRB-TCS-001 — Professional Claims Rejected: Missing Telehealth Taxonomy Code
- **Severity:** P1 | **Recurrence:** First Occurrence | **Version:** TCS 2024.1
- **Summary:** Professional claims with taxonomy code 193200000X (multilingual interpreter) rejected with invalid provider type error.
- **Root Cause:** Taxonomy validation table missing 193200000X and related telehealth taxonomy codes added in NUCC 2024 update.
- **Resolution:** Updated taxonomy reference table with full NUCC 2024 release; added quarterly refresh job.
- **Category:** Integration
- **Cross-system Impact:** TCS taxonomy validation failures prevent claims from reaching Facets or QNXT adjudication. Both claim source systems depend on TCS for pre-validation. TCS failures cascade as "never received" claims — invisible to Facets/QNXT batch monitors.

### PRB-TCS-002 — Line-Level CO-45 Adjustments Overwrite Claim Header
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** TCS 2023.x - 2024.x
- **Summary:** Claim line-level adjustments overwrite entire claim header when adjustment reason code is CO-45.
- **Root Cause:** Adjustment processor applies line-level CO-45 to `claim_total`; header amounts not protected during partial adjust.
- **Resolution:** Isolated adjustment scope to `claim_line_id`; header totals recalculated via aggregate after all line adjustments applied.
- **Category:** Data Integrity

### PRB-TCS-003 — ERA 835 Files Generate Duplicate EOB Records on Resubmission
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** TCS 2023.x - 2024.x
- **Summary:** ERA (835 Electronic Remittance) files generate duplicate EOB records when provider submits resubmission with same ICN.
- **Root Cause:** ERA processor does not check for existing ICN before insert; re-submissions create second EOB record.
- **Resolution:** Added ICN uniqueness check with upsert logic; existing EOBs updated rather than duplicated.
- **Category:** Data Integrity
- **Cross-system Impact:** Duplicate EOB records in TCS compound FRM reconciliation variance (PRB-FRM-002) — FRM sees more payment records than expected, triggering false mismatch alerts.

### PRB-TCS-004 — EOB Letters Mailed to Future-Dated Address Before Effective Date
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** TCS 2024.x
- **Summary:** Explanation of Benefits letters mailed to incorrect address after member moves when `address_effective_date` is future-dated.
- **Root Cause:** `CorrespondenceJob` reads `address_effective_date = TODAY`; future-dated address changes picked up before effective date.
- **Resolution:** Fixed date filter to use `address_effective_date <= SYSDATE`; added 2-day mailing lag buffer.
- **Category:** Correspondence
- **Cross-system Impact:** Address data integrity ties back to Facets Member Enrollment (PRB-FAC-006). Enrollment record truncation means some member address changes never reach TCS — letters sent to old addresses even after the TCS bug fix.

### PRB-TCS-005 — 835 ERA Batch Hangs When NPI Validation Service Degraded
- **Severity:** P1 | **Recurrence:** First Occurrence | **Version:** TCS 2024.1
- **Summary:** 835 ERA batch generation hangs indefinitely when NPI validation service is degraded.
- **Root Cause:** ERA generator calls NPI validation synchronously in main thread; service degradation causes thread pool exhaustion.
- **Resolution:** Moved NPI validation to async background job with circuit breaker; ERA generation proceeds with cached NPI data.
- **Category:** Batch Processing
- **Cross-system Impact:** NPI validation service degradation affects TCS (PRB-TCS-005) and Facets (PRB-FAC-003) simultaneously — both call the same NPI registry. A shared NPI registry circuit breaker at the infrastructure layer would address both.

---

## Summary: EDM / EAM / TCS Issue Patterns

| Product | P1 | P2 | P3 | Top Category |
|---|---|---|---|---|
| EDM | 2 | 2 | 1 | Batch Processing, Data Integrity |
| EAM | 1 | 2 | 1 | Integration (cross-system), Workflow |
| TCS | 2 | 3 | 0 | Data Integrity, Batch Processing |

**Critical Cross-System Integration Chain:** TCS validates → Facets/QNXT adjudicates → EAM authorizes → EDM submits → FRM reconciles. Failures in TCS cascade silently to all downstream systems.
