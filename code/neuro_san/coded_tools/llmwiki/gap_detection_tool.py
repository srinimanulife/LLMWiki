"""
SK-05 · Missing Info Radar — Neuro SAN CodedTool
Wraps the existing llmwiki-skill-gap-detection Lambda.
Sensitive fields arrive via sly_data — never in LLM context.
"""

import logging
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.llmwiki.llmwiki_base_tool import LLMWikiBaseTool

logger = logging.getLogger(__name__)


class GapDetectionTool(CodedTool, LLMWikiBaseTool):
    """
    SK-05: Classifies and records knowledge gaps when WikiQuery returns low/medium confidence.
    Blocking gaps halt the workflow and trigger SNS escalation.
    """

    FUNCTION = os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection")

    def __init__(self):
        LLMWikiBaseTool.__init__(self)

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        """
        :param args: {question, domain, use_case, low_confidence_response}
        :param sly_data: {customer_id, llmwiki_api_key, engagement_id}
        """
        ctx = self._extract_sly(sly_data)
        customer_id             = ctx["customer_id"] or args.get("customer_id", "")
        question                = args.get("question", "").strip()
        domain                  = args.get("domain", "")
        use_case                = args.get("use_case", "UC1")
        low_confidence_response = args.get("low_confidence_response", {})
        invoked_by              = args.get("agent_id", "uc1-neuro-san-agent")

        if not question:
            return {"error": "question is required", "status": "error", "skill_id": "SK-05"}

        payload = {
            "skill":      "GapDetectionSkill",
            "version":    "1.0",
            "invoked_by": invoked_by,
            "inputs": {
                "question":                question,
                "domain":                  domain,
                "use_case":                use_case,
                "customer_id":             customer_id,
                "low_confidence_response": low_confidence_response,
            },
        }

        logger.debug("SK-05 invoke: question=%s", question[:80])
        result = self._invoke_skill(self.FUNCTION, payload)

        if result.get("_error"):
            return {"error": result.get("error"), "status": "error",
                    "skill_id": "SK-05", "gap_count": 0, "blocking": False}

        outputs = result.get("outputs", result)
        return {
            "skill_id":  "SK-05",
            "status":    result.get("status", "success"),
            "gap_count": outputs.get("gap_count", 0),
            "blocking":  outputs.get("blocking", False),
            "gaps":      outputs.get("gaps", []),
            "latency_ms": result.get("latency_ms", 0),
        }
