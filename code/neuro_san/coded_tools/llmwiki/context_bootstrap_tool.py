"""
SK-01 · Customer Briefing Loader — Neuro SAN CodedTool
Wraps the existing llmwiki-skill-context-bootstrap Lambda.
Sensitive fields (customer_id, api_key) arrive via sly_data — never in LLM context.
"""

import logging
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.llmwiki.llmwiki_base_tool import LLMWikiBaseTool

logger = logging.getLogger(__name__)


class ContextBootstrapTool(CodedTool, LLMWikiBaseTool):
    """
    SK-01: Loads customer history + UC playbook in parallel before any agent action.
    Called by UC1SalesToServiceAgent (FrontMan) as the first step in every run.
    """

    FUNCTION = os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap")

    def __init__(self):
        LLMWikiBaseTool.__init__(self)

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        """
        :param args: {use_case, agent_id}
        :param sly_data: {customer_id, llmwiki_api_key, engagement_id}
        """
        ctx = self._extract_sly(sly_data)
        customer_id = ctx["customer_id"] or args.get("customer_id", "")
        use_case    = args.get("use_case", "UC1")
        agent_id    = args.get("agent_id", "uc1-neuro-san-agent")

        payload = {
            "skill":      "ContextBootstrapSkill",
            "version":    "1.0",
            "invoked_by": agent_id,
            "inputs": {
                "customer_id": customer_id,
                "use_case":    use_case,
                "agent_id":    agent_id,
            },
        }

        logger.debug("SK-01 invoke: customer=%s use_case=%s", customer_id, use_case)
        result = self._invoke_skill(self.FUNCTION, payload)

        if result.get("_error"):
            return {"error": result.get("error"), "status": "error",
                    "skill_id": "SK-01", "customer_status": "unknown"}

        outputs = result.get("outputs", result)
        return {
            "skill_id":         "SK-01",
            "status":           result.get("status", "success"),
            "customer_status":  outputs.get("customer_status", "unknown"),
            "pages_loaded":     outputs.get("pages_loaded", 0),
            "key_facts":        outputs.get("customer_context", {}).get("key_facts", []),
            "playbook_steps":   outputs.get("playbook", {}).get("steps", []),
            "prior_contributions": outputs.get("prior_contributions", []),
            "latency_ms":       result.get("latency_ms", 0),
        }
