"""
SK-02 · Knowledge Finder — Neuro SAN CodedTool
Wraps the existing llmwiki-skill-wiki-query Lambda.
Sensitive fields arrive via sly_data — never in LLM context.
"""

import logging
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.llmwiki.llmwiki_base_tool import LLMWikiBaseTool

logger = logging.getLogger(__name__)


class WikiQueryTool(CodedTool, LLMWikiBaseTool):
    """
    SK-02: Domain-scoped semantic search of the LLMWiki knowledge base.
    Returns answer, confidence level, and source citations.
    """

    FUNCTION = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")

    def __init__(self):
        LLMWikiBaseTool.__init__(self)

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        """
        :param args: {question, domain, use_case}
        :param sly_data: {customer_id, llmwiki_api_key, engagement_id}
        """
        ctx = self._extract_sly(sly_data)
        customer_id = ctx["customer_id"] or args.get("customer_id", "")
        question    = args.get("question", "").strip()
        domain      = args.get("domain", "")
        use_case    = args.get("use_case", "UC1")
        invoked_by  = args.get("agent_id", "uc1-neuro-san-agent")

        if not question:
            return {"error": "question is required", "status": "error", "skill_id": "SK-02"}

        payload = {
            "skill":      "WikiQuerySkill",
            "version":    "1.0",
            "invoked_by": invoked_by,
            "inputs": {
                "question":    question,
                "domain":      domain,
                "customer_id": customer_id,
                "use_case":    use_case,
                "intent":      "handoff-preparation",
            },
        }

        logger.debug("SK-02 invoke: question=%s domain=%s", question[:80], domain)
        result = self._invoke_skill(self.FUNCTION, payload)

        if result.get("_error"):
            return {"error": result.get("error"), "status": "error",
                    "skill_id": "SK-02", "confidence": "low"}

        outputs = result.get("outputs", result)
        return {
            "skill_id":        "SK-02",
            "status":          result.get("status", "success"),
            "confidence":      outputs.get("confidence", "low"),
            "answer":          outputs.get("answer", ""),
            "action_items":    outputs.get("action_items", []),
            "sources":         outputs.get("sources", []),
            "wiki_page_count": result.get("wiki_pages_used", 0),
            "latency_ms":      result.get("latency_ms", 0),
        }
