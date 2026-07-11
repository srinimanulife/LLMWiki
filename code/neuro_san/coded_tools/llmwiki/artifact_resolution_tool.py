"""
SK-04 · Template Auto-Fill — Neuro SAN CodedTool
Wraps the existing llmwiki-skill-artifact-resolution Lambda.
Sensitive fields arrive via sly_data — never in LLM context.
"""

import logging
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.llmwiki.llmwiki_base_tool import LLMWikiBaseTool

logger = logging.getLogger(__name__)


class ArtifactResolutionTool(CodedTool, LLMWikiBaseTool):
    """
    SK-04: Finds a wiki template and populates every field with customer context.
    Returns completion_pct and the filled markdown document.
    """

    FUNCTION = os.environ.get("SK04_FUNCTION", "llmwiki-skill-artifact-resolution")

    def __init__(self):
        LLMWikiBaseTool.__init__(self)

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        """
        :param args: {artifact_type, available_context, use_case}
        :param sly_data: {customer_id, llmwiki_api_key, engagement_id}
        """
        ctx = self._extract_sly(sly_data)
        customer_id       = ctx["customer_id"] or args.get("customer_id", "")
        artifact_type     = args.get("artifact_type", "persona-template")
        available_context = args.get("available_context", {})
        use_case          = args.get("use_case", "UC1")
        invoked_by        = args.get("agent_id", "uc1-neuro-san-agent")

        # Inject customer_id into context so the Lambda has full picture
        if customer_id and "customer_id" not in available_context:
            available_context = dict(available_context, customer_id=customer_id)

        payload = {
            "skill":      "ArtifactResolutionSkill",
            "version":    "1.0",
            "invoked_by": invoked_by,
            "inputs": {
                "artifact_type":     artifact_type,
                "customer_id":       customer_id,
                "available_context": available_context,
                "use_case":          use_case,
            },
        }

        logger.debug("SK-04 invoke: artifact=%s customer=%s", artifact_type, customer_id)
        result = self._invoke_skill(self.FUNCTION, payload)

        if result.get("_error"):
            return {"error": result.get("error"), "status": "error",
                    "skill_id": "SK-04", "found": False, "completion_pct": 0}

        outputs = result.get("outputs", result)
        return {
            "skill_id":        "SK-04",
            "status":          result.get("status", "success"),
            "found":           outputs.get("found", False),
            "completion_pct":  outputs.get("completion_pct", 0),
            "populated_fields": outputs.get("populated_fields", []),
            "missing_fields":  outputs.get("missing_fields", []),
            "artifact_content": outputs.get("artifact_content", ""),
            "latency_ms":      result.get("latency_ms", 0),
        }
