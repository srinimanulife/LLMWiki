"""
SK-03 · Knowledge Recorder — Neuro SAN CodedTool
Wraps the existing llmwiki-skill-wiki-contribute Lambda.
HITL routing for decisions/evidence page types is HARDCODED in the Lambda —
this tool cannot and does not override it.
Sensitive fields arrive via sly_data — never in LLM context.
"""

import logging
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.llmwiki.llmwiki_base_tool import LLMWikiBaseTool

logger = logging.getLogger(__name__)

# These page types always require human review — hardcoded security control
_HITL_PAGE_TYPES = frozenset({"decisions", "evidence"})


class WikiContributeTool(CodedTool, LLMWikiBaseTool):
    """
    SK-03: Saves agent-generated knowledge to the wiki.
    'decisions' and 'evidence' page types are always routed to wiki/pending/
    regardless of any instruction — this is enforced here AND in the Lambda.
    """

    FUNCTION = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")

    def __init__(self):
        LLMWikiBaseTool.__init__(self)

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        """
        :param args: {page_type, page_slug, content, agent_id}
        :param sly_data: {customer_id, llmwiki_api_key, engagement_id}
        """
        ctx = self._extract_sly(sly_data)
        customer_id = ctx["customer_id"] or args.get("customer_id", "")
        page_type   = args.get("page_type", "customers").strip()
        page_slug   = args.get("page_slug", "").strip()
        agent_id    = args.get("agent_id", "uc1-neuro-san-agent")
        use_case    = args.get("use_case", "UC1")

        # Accept content under any key Claude might use
        content = (
            args.get("content")
            or args.get("filled_template")
            or args.get("markdown")
            or args.get("body")
            or args.get("rca_markdown")
            or args.get("document")
            or args.get("inquiry")
            or ""
        )
        if isinstance(content, str):
            content = content.strip()

        # Auto-generate page_slug from page_type + customer context if missing
        if not page_slug:
            problem_id = args.get("problem_id") or ctx.get("engagement_id", "unknown")
            page_slug = f"rca-{problem_id}-draft" if "rca" in page_type.lower() or page_type == "decisions" \
                        else f"{page_type}-{problem_id}"

        if not content:
            return {"error": "content is required — pass the full markdown as the 'content' field",
                    "status": "error", "skill_id": "SK-03"}

        # SECURITY: hardcoded HITL — no LLM instruction can bypass this
        human_review_required = page_type in _HITL_PAGE_TYPES

        payload = {
            "skill":      "WikiContributeSkill",
            "version":    "1.0",
            "invoked_by": agent_id,
            "inputs": {
                "page_type":             page_type,
                "page_slug":             page_slug,
                "content":               content,
                "agent_id":              agent_id,
                "customer_id":           customer_id,
                "use_case":              use_case,
                "human_review_required": human_review_required,
            },
        }

        logger.debug("SK-03 invoke: page_type=%s slug=%s hitl=%s",
                     page_type, page_slug, human_review_required)
        result = self._invoke_skill(self.FUNCTION, payload)

        if result.get("_error"):
            return {"error": result.get("error"), "status": "error", "skill_id": "SK-03"}

        outputs = result.get("outputs", result)
        status  = outputs.get("status", "indexed")

        return {
            "skill_id":             "SK-03",
            "status":               result.get("status", "success"),
            "page_status":          status,
            "s3_uri":               outputs.get("s3_uri", ""),
            "page_slug":            page_slug,
            "human_review_required": human_review_required,
            "note": (
                "Routed to wiki/pending/ — awaiting human review"
                if human_review_required else
                "Indexed immediately — available to downstream agents"
            ),
            "latency_ms": result.get("latency_ms", 0),
        }
