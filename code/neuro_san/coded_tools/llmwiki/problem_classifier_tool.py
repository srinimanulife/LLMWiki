"""
SK-06 · Problem Classifier — Neuro SAN CodedTool
Wraps the existing llmwiki-skill-problem-classifier Lambda.
Classifies a problem record into category, recurrence type, and risk tier.
"""

import logging
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.llmwiki.llmwiki_base_tool import LLMWikiBaseTool

logger = logging.getLogger(__name__)


class ProblemClassifierTool(CodedTool, LLMWikiBaseTool):
    """
    SK-06: Problem classifier — normalises category, recurrence, risk tier.
    Alerts ops via SNS for P1/High severity before the LLM call.
    """

    FUNCTION = os.environ.get("SK06_FUNCTION", "llmwiki-skill-problem-classifier")

    def __init__(self):
        LLMWikiBaseTool.__init__(self)

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        """
        :param args: {problem_id, product, component, severity, problem_summary,
                      related_records, ingest_batch_id}
        :param sly_data: {customer_id, llmwiki_api_key, engagement_id}
        """
        ctx            = self._extract_sly(sly_data)
        problem_id     = args.get("problem_id", "").strip()
        product        = args.get("product", "").strip()
        component      = args.get("component", "").strip()
        severity       = args.get("severity", "").strip()
        problem_summary = args.get("problem_summary", "").strip()
        related_records = args.get("related_records", [])
        ingest_batch_id = args.get("ingest_batch_id", ctx.get("engagement_id", ""))
        invoked_by     = args.get("agent_id", "pm-neuro-san-agent")

        # Fallback: if Claude packed everything into "inquiry" string, parse it out
        if not problem_id:
            inquiry = args.get("inquiry", "")
            if inquiry:
                import re as _re
                m = _re.search(r'\b(PRB[\w-]+|PROB[\w-]+|INC[\w-]+)', inquiry, _re.IGNORECASE)
                if m:
                    problem_id = m.group(1)
            if not problem_id:
                problem_id = args.get("mode", "")  # last resort — unlikely but safe
        if not product:
            inquiry = args.get("inquiry", "")
            for candidate in ["QNXT", "Facets", "FACETS", "EAM", "EDM", "TCS"]:
                if candidate.lower() in inquiry.lower():
                    product = candidate
                    break
        if not component:
            component = args.get("inquiry", "")[:200]  # pass full inquiry as summary if no component
        if not problem_summary and args.get("inquiry"):
            problem_summary = args.get("inquiry", "")[:500]

        if not problem_id:
            return {"error": "problem_id is required — pass it as a named field, e.g. problem_id='PRB0042'",
                    "status": "error", "skill_id": "SK-06"}
        if not product:
            return {"error": "product is required (QNXT, Facets, EAM, EDM, or TCS)",
                    "status": "error", "skill_id": "SK-06"}

        payload = {
            "skill":      "ProblemClassifierSkill",
            "version":    "1.0",
            "invoked_by": invoked_by,
            "inputs": {
                "problem_id":      problem_id,
                "product":         product,
                "component":       component,
                "severity":        severity,
                "problem_summary": problem_summary,
                "related_records": related_records,
                "ingest_batch_id": ingest_batch_id,
            },
        }

        logger.debug("SK-06 invoke: problem_id=%s product=%s severity=%s",
                     problem_id, product, severity)
        result = self._invoke_skill(self.FUNCTION, payload)

        if result.get("_error"):
            return {"error": result.get("error"), "status": "error", "skill_id": "SK-06"}

        outputs = result.get("outputs", result)
        return {
            "skill_id":                  "SK-06",
            "status":                    result.get("status", "success"),
            "normalized_category":       outputs.get("normalized_category", ""),
            "recurrence_type":           outputs.get("recurrence_type", "unique"),
            "risk_tier":                 outputs.get("risk_tier", "low"),
            "classification_confidence": outputs.get("classification_confidence", ""),
            "classification_notes":      outputs.get("classification_notes", ""),
            "alert_sent":                outputs.get("alert_sent", False),
            "latency_ms":                result.get("latency_ms", 0),
        }
