# Problem Management → LLMWiki / Harness
## Sample Outputs Pack

---

# 1. WIKI PAGE OUTPUTS

---

## 1.1 QNXT RCA (Repeated Problem)

---
page_type: rca  
page_slug: qnxt-member-eligibility-timeout  
product: QNXT  
related_problem_id: PRB-1001  
issue_pattern: repeated  
---

### Summary
Repeated timeout observed in Member Update API and EligibilityBatch.

### Symptoms
- API timeout during eligibility update
- Batch failures for large member updates

### Root Cause (Hypothesis)
Timeout limits insufficient for high-volume update operations.

### Evidence
- APPLOG-0001
- INC-QNXT-1042
- PRB-1001

### Solution
Repeated problem – increase timeout, add retry logic, introduce batch chunking.

### Reuse Guidance
Link all future similar timeout issues to this RCA.

---

## 1.2 TCS Incident (Unique Problem)

---
page_type: incidents  
page_slug: tcs-print-vendor-feed-delay  
product: TCS  
issue_pattern: unique  
---

### Summary
Print vendor feed delayed beyond SLA window.

### Symptoms
- Package not delivered on time
- No recurring evidence

### Solution
Unique problem – resend package and track vendor SLA exception.

### Reuse Guidance
Treat as unique unless pattern repeats.

---

## 1.3 EAM Known Error (Repeated Problem)

---
page_type: known-error  
page_slug: eam-trr-backlog  
product: EAM  
issue_pattern: repeated  
---

### Summary
TRR ingestion processing causes recurring backlog.

### Symptoms
- Exception queue growth
- Batch ingestion delay

### Solution
Repeated problem – increase ingestion capacity, split files, tune queue.

### Reuse Guidance
Attach future incidents to this known error.

---

## 1.4 EDM Evidence / RCA

---
page_type: evidence  
page_slug: edm-277ca-rejection-spike  
product: EDM  
issue_pattern: repeated  
---

### Summary
Repeated rejection spike found in 277CA acknowledgements.

### Symptoms
- High rejection rate
- Member ID mismatch

### Solution
Repeated problem – validate IDs prior to submission, fix parser logic.

### Governance
Requires human approval before applying changes.

---

# 2. API OUTPUTS (/wiki/ask)

---

## 2.1 QNXT Repeated Problem Response

```json
{
  "answer": "Repeated timeout issue identified in Member Update API.",
  "confidence": "high",
  "issue_pattern": "repeated",
  "action_items": [
    "Increase timeout",
    "Add retry logic",
    "Split batch processing"
  ],
  "sources": ["PRB-1001", "APPLOG-0001"]
}