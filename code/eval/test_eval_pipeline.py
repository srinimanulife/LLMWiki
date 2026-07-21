"""
pytest test suite for the Phoenix eval pipeline.

Tests run fully offline (mock mode, no Phoenix required, no AWS).
They validate the eval logic itself — not the quality of LLMWiki answers.

Run:
    cd code
    pytest eval/test_eval_pipeline.py -v
    pytest eval/test_eval_pipeline.py -v -k "step3"   # only step3 tests
"""

import csv
import os
import sys
import tempfile
import pytest

# Make eval modules importable
sys.path.insert(0, os.path.dirname(__file__))

# ── Step 2 tests ──────────────────────────────────────────────────────────

from step2_read_traces import categorise, analyse

# Representative synthetic spans that cover every category
SEED_SPANS = [
    {
        "span_id": "s001", "name": "llmwiki.query",
        "input": "What is the SIT sign-off criteria?",
        "output": "SIT sign-off requires P1/P2 defects resolved and claims volume test at 110% peak. "
                  "[[sk-02-knowledge-finder]]",
        "context": "The testing playbook defines SIT exit criteria including defect density threshold "
                   "and transaction validation. Source: wiki/skills/sk-02-knowledge-finder.md",
        "confidence": "high", "domain": "testing", "citations": "3", "latency_ns": 2100000000,
    },
    {
        "span_id": "s002", "name": "llmwiki.query",
        "input": "What is the audit log retention policy?",
        "output": "",  # empty answer
        "context": "Some context about TriZetto audit configurations.",
        "confidence": "low", "domain": "compliance", "citations": "0", "latency_ns": 500000000,
    },
    {
        "span_id": "s003", "name": "llmwiki.query",
        "input": "What is the ARB security checklist?",
        "output": "ARB security requires VPC isolation, IAM least-privilege, and CloudTrail logging.",
        "context": "",  # no context
        "confidence": "high", "domain": "provisioning", "citations": "0", "latency_ns": 1500000000,
    },
    {
        "span_id": "s004", "name": "llmwiki.query",
        "input": "What is the BOM for QNXT?",
        "output": "The QNXT BOM includes EC2 application tier, RDS SQL Server Multi-AZ, and ALB.",
        "context": "",  # no context AND high confidence with 0 citations
        "confidence": "high", "domain": "provisioning", "citations": "0", "latency_ns": 1800000000,
    },
    {
        "span_id": "s005", "name": "llmwiki.query",
        "input": "What is the cutover criteria for Facets?",
        "output": "The wiki has limited information on Facets cutover criteria.",
        "context": "Partial context: cutover requires data migration dry run.",
        "confidence": "low", "domain": "cutover", "citations": "1", "latency_ns": 2500000000,
    },
]


class TestStep2Categorise:
    def test_ok_span(self):
        span = SEED_SPANS[0]
        assert categorise(span) == "ok"

    def test_empty_answer(self):
        span = SEED_SPANS[1]
        assert categorise(span) == "empty_answer"

    def test_no_context_is_categorised(self):
        span = SEED_SPANS[2]
        # no context → no_context (confidence_calibration checked second)
        assert categorise(span) == "no_context"

    def test_overconfident(self):
        # high confidence + 0 citations + no context → no_context takes precedence
        span = {**SEED_SPANS[3], "confidence": "high", "citations": "0", "context": ""}
        cat = categorise(span)
        assert cat in ("no_context", "overconfident")

    def test_low_confidence(self):
        span = SEED_SPANS[4]
        assert categorise(span) == "low_confidence"

    def test_analyse_counts(self):
        result = analyse(SEED_SPANS)
        counts = result["counts"]
        total = sum(counts.values())
        assert total == len(SEED_SPANS)
        assert counts["ok"] >= 1
        assert counts["empty_answer"] >= 1


# ── Step 3 tests ──────────────────────────────────────────────────────────

from step3_run_evals import (
    eval_has_answer,
    eval_citation_present,
    eval_confidence_calibrated,
    run_code_evals,
    run_faithfulness_evals,
    run_biz_api_eval,
)


class TestStep3CodeEvals:
    def test_has_answer_pass(self):
        row = {"output": "This is a sufficiently long answer that passes the check."}
        result = eval_has_answer(row)
        assert result["label"] == "pass"
        assert result["score"] == 1

    def test_has_answer_fail(self):
        row = {"output": ""}
        result = eval_has_answer(row)
        assert result["label"] == "fail"
        assert result["score"] == 0

    def test_citation_present_pass(self):
        row = {"citations": "3"}
        result = eval_citation_present(row)
        assert result["label"] == "pass"

    def test_citation_present_fail(self):
        row = {"citations": "0"}
        result = eval_citation_present(row)
        assert result["label"] == "fail"

    def test_confidence_calibrated_pass(self):
        row = {"citations": "3", "confidence": "high"}
        result = eval_confidence_calibrated(row)
        assert result["label"] == "pass"

    def test_confidence_calibrated_fail_overconfident(self):
        row = {"citations": "0", "confidence": "high"}
        result = eval_confidence_calibrated(row)
        assert result["label"] == "fail"

    def test_confidence_calibrated_low_conf_ok(self):
        # low confidence with 0 citations is calibrated (honest)
        row = {"citations": "0", "confidence": "low"}
        result = eval_confidence_calibrated(row)
        assert result["label"] == "pass"

    def test_run_code_evals_returns_results(self):
        rows = [
            {"span_id": "x1", "input": "Q1", "output": "A long enough answer here.",
             "citations": "2", "confidence": "high"},
            {"span_id": "x2", "input": "Q2", "output": "",
             "citations": "0", "confidence": "low"},
        ]
        results = run_code_evals(rows)
        # 3 evals × 2 rows = 6 result rows
        assert len(results) == 6
        evals = {r["eval"] for r in results}
        assert "has_answer" in evals
        assert "citation_present" in evals
        assert "confidence_calibrated" in evals


class TestStep3FaithfulnessEvalMock:
    def test_mock_faithful_on_context(self):
        rows = [
            {
                "span_id": "f1",
                "input": "What is SIT sign-off?",
                "output": "SIT requires P1/P2 defect resolution. [[testing-runbook]]",
                "context": "SIT exit criteria: defects resolved, volume test passed.",
                "confidence": "high", "domain": "testing", "citations": "3",
            }
        ]
        results = run_faithfulness_evals(rows, mock=True)
        assert len(results) == 1
        assert results[0]["claude_label"] in ("faithful", "hallucinated")

    def test_mock_skips_no_context(self):
        rows = [
            {
                "span_id": "f2",
                "input": "What is X?",
                "output": "X is ...",
                "context": "",  # no context — should be skipped
                "confidence": "low", "domain": "unknown", "citations": "0",
            }
        ]
        results = run_faithfulness_evals(rows, mock=True)
        # span with no context is filtered out
        assert len(results) == 0

    def test_mock_returns_labels(self):
        rows = [
            {
                "span_id": "f3",
                "input": "Q",
                "output": "Long enough answer with [[citation]]",
                "context": "Sufficient context with details about the topic in question.",
                "confidence": "high", "domain": "testing", "citations": "2",
            }
        ]
        results = run_faithfulness_evals(rows, mock=True)
        assert results[0]["claude_label"] in ("faithful", "hallucinated")
        assert results[0]["nova_label"] in ("faithful", "hallucinated")
        assert isinstance(results[0]["judges_agree"], bool)


class TestStep3BizApiEvalMock:
    def test_pass_on_high_confidence(self):
        rows = [{"span_id": "b1", "input": "Q",
                 "output": "A sufficiently long answer that passes the minimum length filter.",
                 "context": "some context", "confidence": "high", "citations": "3", "domain": "test"}]
        results = run_biz_api_eval(rows, mock=True)
        assert results[0]["biz_api_label"] == "PASS"

    def test_fail_on_low_confidence(self):
        rows = [{"span_id": "b2", "input": "Q",
                 "output": "A sufficiently long answer that passes the minimum length filter.",
                 "context": "some context", "confidence": "low", "citations": "0", "domain": "test"}]
        results = run_biz_api_eval(rows, mock=True)
        assert results[0]["biz_api_label"] == "FAIL"

    def test_skip_short_output(self):
        rows = [{"span_id": "b3", "input": "Q", "output": "short",
                 "context": "ctx", "confidence": "high", "citations": "1", "domain": "test"}]
        results = run_biz_api_eval(rows, mock=True)
        assert len(results) == 0  # filtered out (output < 20 chars)


# ── Step 3 save/load CSV round-trip ───────────────────────────────────────

class TestStep3SaveResults:
    def test_save_and_reload(self):
        from step3_run_evals import save_results
        code_results  = [{"span_id": "z1", "eval": "has_answer", "label": "pass",
                           "score": 1, "explanation": "ok", "question": "Q1"}]
        faith_results = [{"span_id": "z1", "domain": "test", "confidence": "high",
                          "question": "Q1", "claude_label": "faithful",
                          "nova_label": "faithful", "judges_agree": True,
                          "claude_explanation": "ok", "nova_explanation": "ok"}]
        biz_results   = [{"span_id": "z1", "domain": "test",
                          "biz_api_label": "PASS", "biz_api_explanation": "ok"}]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv",
                                         delete=False) as f:
            path = f.name

        try:
            save_results(code_results, faith_results, biz_results, path)
            assert os.path.exists(path)
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
            assert len(rows) >= 1
            assert rows[0]["claude_label"] == "faithful"
            assert rows[0]["biz_api_label"] == "PASS"
        finally:
            os.unlink(path)


# ── Step 4 tests ──────────────────────────────────────────────────────────

from step4_judge_comparison import report as judge_report


class TestStep4Report:
    def test_report_runs_without_error(self, capsys):
        rows = [
            {"span_id": "j1", "domain": "testing", "confidence": "high",
             "question": "Q1", "claude_label": "faithful", "nova_label": "faithful",
             "judges_agree": "True"},
            {"span_id": "j2", "domain": "provisioning", "confidence": "medium",
             "question": "Q2", "claude_label": "faithful", "nova_label": "hallucinated",
             "judges_agree": "False"},
            {"span_id": "j3", "domain": "testing", "confidence": "low",
             "question": "Q3", "claude_label": "hallucinated", "nova_label": "hallucinated",
             "judges_agree": "True"},
        ]
        judge_report(rows)
        captured = capsys.readouterr()
        assert "Judge" in captured.out
        assert "agreement" in captured.out.lower()
        assert "Disagreements" in captured.out

    def test_report_no_labels_warns(self, capsys):
        rows = [{"span_id": "j4", "claude_label": "", "nova_label": ""}]
        judge_report(rows)
        captured = capsys.readouterr()
        assert "No faithfulness labels" in captured.out


# ── Step 5 tests ──────────────────────────────────────────────────────────

from step5_experiments import (
    GOLDEN_DATASET, task_mock, judge_faithfulness, compare_variants,
)


class TestStep5Experiments:
    def test_task_mock_v1(self):
        ex = GOLDEN_DATASET[0]
        out = task_mock(ex, "v1")
        assert "answer" in out
        assert len(out["answer"]) > 0

    def test_task_mock_v2_has_citation(self):
        ex = GOLDEN_DATASET[0]
        out = task_mock(ex, "v2")
        # v2 answers include a [[citation]]
        assert "[[" in out["answer"]

    def test_judge_mock_faithful_with_context(self):
        label = judge_faithfulness(
            answer="Detailed answer with [[citation]]",
            question="What is X?",
            context="Some context with details about X.",
            mock=True,
        )
        assert label == "faithful"

    def test_judge_mock_hallucinated_empty_context(self):
        label = judge_faithfulness(
            answer="answer",
            question="Q",
            context="",
            mock=True,
        )
        assert label == "hallucinated"

    def test_compare_variants_runs(self, capsys):
        v1 = [{"domain": "test", "label": "faithful"},
              {"domain": "test", "label": "hallucinated"}]
        v2 = [{"domain": "test", "label": "faithful"},
              {"domain": "test", "label": "faithful"}]
        compare_variants(v1, v2)
        captured = capsys.readouterr()
        assert "v1" in captured.out
        assert "v2" in captured.out
        assert "Delta" in captured.out

    def test_full_mock_run(self, tmp_path):
        from step5_experiments import run_variant, save_experiments
        v1 = run_variant(GOLDEN_DATASET[:3], "v1", "mock", True)
        v2 = run_variant(GOLDEN_DATASET[:3], "v2", "mock", True)
        assert len(v1) == 3
        assert len(v2) == 3
        assert all(r["label"] in ("faithful", "hallucinated") for r in v1 + v2)
        out_path = str(tmp_path / "exp.csv")
        save_experiments(v1, v2, out_path)
        assert os.path.exists(out_path)
