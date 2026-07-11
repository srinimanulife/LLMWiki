# NetworX and FRM — Known Issues & Problem Records

## NetworX — Provider Fee Schedule & Contract Management

**Product:** NetworX (TriZetto/Cognizant)
**Domain:** Fee Schedule Management, Payer-Provider Contract Administration, Network Adequacy
**Role in TriZetto Suite:** Manages payer-provider contracts and fee schedules used by Facets and QNXT during claims adjudication. NetworX rates are the authoritative pricing source — incorrect rates in NetworX cause systemic adjudication errors across all claims in both Facets and QNXT.

---

### PRB-NETWORX-001 — Fee Schedule Rollover Not Applied to In-Progress Claims
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** NX 8.1.x - 8.3.x
- **Summary:** Fee schedule effective date rollover does not apply new rates to in-progress claims that span the rollover date.
- **Root Cause:** `ClaimAdjudicator` reads fee schedule once at claim receipt date; mid-processing rate changes not re-evaluated.
- **Resolution:** Added fee schedule re-read at adjudication time using `service_date` rather than `received_date`.
- **Category:** Data Integrity
- **Cross-system Impact:** NetworX fee schedule rollover failures cause systematic rate misapplication in both Facets and QNXT claims batches. Any Facets batch processing issue (PRB-FAC-001) during a fee schedule rollover window compounds the problem — claims fail AND rates are wrong when they retry.

### PRB-NETWORX-002 — Overlapping Contracts Cause Non-Deterministic Rate Selection
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** NX 8.2.x - 8.3.x
- **Summary:** Payer-provider contract terms not applied to facility claims when facility has multiple active contracts with overlapping effective dates.
- **Root Cause:** `ContractSelector` returns first matching contract; overlapping contracts cause non-deterministic selection.
- **Resolution:** Implemented contract priority ranking with specificity score; most-specific contract (by TIN + NPI + service type) selected.
- **Category:** Business Logic
- **Cross-system Impact:** Non-deterministic contract selection means the same claim adjudicated on different days may pay different amounts. This directly causes FRM reconciliation variances (PRB-FRM-002) — FRM sees different payment amounts for the same claim depending on which contract was selected.

### PRB-NETWORX-003 — Radiology Modifier 26 Billed as Global After MPFS 2025 Update
- **Severity:** P2 | **Recurrence:** First Occurrence | **Version:** NX 8.3.0
- **Summary:** Radiology fee schedule modifier 26 (professional component) billed as global fee after MPFS 2025 update.
- **Root Cause:** Modifier table not refreshed with MPFS 2025 physician fee schedule; modifier 26 split billing flag set to global.
- **Resolution:** Updated MPFS table with 2025 release; added annual regulatory refresh process tied to CMS publication calendar.
- **Category:** Data Integrity
- **Cross-system Impact:** Modifier 26 overbilling affects all Facets and QNXT radiology claims processed after the MPFS 2025 effective date. TCS (PRB-TCS-001) has a parallel regulatory refresh failure — taxonomy codes not updated for NUCC 2024. Both represent systemic gaps in regulatory reference data maintenance.

### PRB-NETWORX-004 — Network Adequacy Report Undercounts Rural Specialists
- **Severity:** P3 | **Recurrence:** Recurring | **Version:** NX 8.x
- **Summary:** Network adequacy report undercounts in-network specialists for rural counties with shared ZIP code boundaries.
- **Root Cause:** County-to-ZIP mapping uses centroid ZIP only; providers in border ZIP codes excluded from rural county count.
- **Resolution:** Switched to full ZIP-to-county crosswalk table; rural adequacy counts improved by average 12% across 34 counties.
- **Category:** Reporting

---

## FRM — Financial Reconciliation Manager (Standalone)

**Product:** FRM (TriZetto/Cognizant Financial Reconciliation Manager)
**Domain:** Capitation Reconciliation, Premium Reconciliation, Financial Audit
**Role in TriZetto Suite:** Month-end financial reconciliation layer that aggregates capitation postings from both Facets and QNXT, premium data from Facets, and encounter data from EDM. FRM is the final financial checkpoint — discrepancies here represent the cumulative effect of upstream data quality issues across all systems.

---

### PRB-FRM-001 — Month-End Reconciliation Deadlock Between Facets and QNXT Capitation Postings
- **Severity:** P1 | **Recurrence:** Recurring | **Version:** FRM 3.1.x
- **Summary:** Month-end reconciliation fails to balance when Facets and QNXT post capitation adjustments in the same batch window.
- **Root Cause:** FRM assumes sequential posting; concurrent Facets and QNXT postings create race condition in `fin_ledger_entry` table.
- **Resolution:** Added pessimistic row-level lock per `source_system` during capitation posting; batch coordination via lock manager.
- **Category:** Batch Processing
- **Cross-system Impact:** This is the primary Facets-vs-QNXT cross-system failure point in FRM. QNXT capitation duplicate rows (PRB-QNXT-007) and Facets FRM deadlock (PRB-FAC-010) both contribute to this failure. Even after the FRM lock fix, upstream capitation data quality issues from both source systems continue to cause reconciliation variances.

### PRB-FRM-002 — False Variances for Retroactive Enrollment Adjustments Across Fiscal Months
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** FRM 3.0.x - 3.1.x
- **Summary:** Premium reconciliation report shows false variances for retroactive enrollment adjustments spanning multiple fiscal months.
- **Root Cause:** Retroactive adjustments posted to current period only; prior-period ledger entries not restated.
- **Resolution:** Implemented period-aware retroactive posting with automatic prior-period restatement entries.
- **Category:** Data Integrity
- **Cross-system Impact:** Upstream sources of retroactive adjustments: Facets PRB-FAC-004 (premium miscalculation at age-boundary), QNXT PRB-QNXT-007 (duplicate capitation rows), TCS PRB-TCS-003 (duplicate EOB records), NetworX PRB-NETWORX-002 (non-deterministic contract selection). FRM cannot balance if any of these upstream issues are active.

### PRB-FRM-003 — FRM-to-EDM Encounter Count Mismatch Alerts Fire on Valid Supplemental Submissions
- **Severity:** P2 | **Recurrence:** Recurring | **Version:** FRM 3.1.x
- **Summary:** FRM-to-EDM encounter count mismatch alerts triggering for valid supplemental data submissions.
- **Root Cause:** Mismatch threshold set to 0%; supplemental submissions legitimately exceed original encounter counts.
- **Resolution:** Changed threshold to 5% with directional flag; supplemental increases no longer alert; decreases still alert.
- **Category:** Business Logic
- **Cross-system Impact:** EDM supplemental data ingestion (PRB-EDM-005) and FRM mismatch thresholds interact — when EDM supplemental submissions are large (edge case) AND FRM threshold is 0%, FRM generates false critical alerts that mask real reconciliation failures.

### PRB-FRM-004 — DCSA Audit Trail Incomplete for EDM-Initiated Adjustments
- **Severity:** P3 | **Recurrence:** Recurring | **Version:** FRM 3.0.x - 3.1.x
- **Summary:** DCSA audit trail incomplete — FRM log omits `batch_id` for adjustments initiated from EDM interface.
- **Root Cause:** EDM-initiated adjustments bypass FRM batch controller; log entry written without `batch_id` context.
- **Resolution:** Routed all EDM-initiated adjustments through FRM batch controller; `batch_id` now populated for all entries.
- **Category:** Reporting
- **Cross-system Impact:** Pairs with EDM RADV extract incompleteness (PRB-EDM-004). During RADV audits, FRM cannot provide a complete audit trail for EDM-originated encounters, and EDM cannot provide complete extract data — both systems independently incomplete during the same audit event.

---

## Cross-System Integration Map: Facets and QNXT as Claim Source Systems

```
EXTERNAL CLAIMS
      │
      ▼
   [TCS — Claims Intake & Validation]
   PRB-TCS-001 taxonomy rejection cascades to Facets/QNXT
   PRB-TCS-005 NPI batch hang blocks remittance
      │
      ├──────────────────────────┐
      ▼                          ▼
[FACETS — Claims Source]    [QNXT — Claims Source]
PRB-FAC-001 batch P1        PRB-QNXT-001 batch P1
PRB-FAC-002 eligibility     PRB-QNXT-003 COB cache
PRB-FAC-004 premium calc    PRB-QNXT-004 eligibility
PRB-FAC-005 duplicate       PRB-QNXT-002 duplicate
PRB-FAC-006 enrollment      PRB-QNXT-005 provider
PRB-FAC-007 auth cache      PRB-QNXT-006 auth SLA
      │                          │
      └────────────┬─────────────┘
                   ▼
           [EAM — Authorization]
           PRB-EAM-002 no event propagation → Facets/QNXT
           PRB-EAM-001 DME misrouting
           PRB-EAM-004 weekend SLA gap
                   │
                   ▼
           [NetworX — Fee Schedules]
           PRB-NETWORX-002 contract selection
           PRB-NETWORX-001 rate rollover
                   │
                   ▼
           [EDM — Encounter Submission]
           PRB-EDM-001 batch fail-fast
           PRB-EDM-003 RAF exclusion
                   │
                   ▼
           [FRM — Reconciliation]
           PRB-FRM-001 Facets+QNXT deadlock
           PRB-FRM-002 retroactive variance
```

## NetworX / FRM Summary

| Category | Count | Cross-System Risk |
|---|---|---|
| Batch Processing | 2 | FRM-001: direct Facets+QNXT deadlock |
| Data Integrity | 3 | NetworX rates cascade to all claims |
| Business Logic | 2 | Non-deterministic contract / mismatch threshold |
| Reporting | 2 | RADV audit gaps + network adequacy |
