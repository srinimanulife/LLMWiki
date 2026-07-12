"""
EchoTool — local dev stub CodedTool.
No Lambda, no AWS calls. Used to verify the local Neuro SAN stack end-to-end.
"""

import datetime
import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

logger = logging.getLogger(__name__)


class EchoTool(CodedTool):
    """Stub tool: echoes args back. No external dependencies."""

    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        message   = args.get("message", "")
        user_name = args.get("user_name", "tester")
        ts        = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.debug("EchoTool invoked: user=%s msg=%s", user_name, message[:60])

        return {
            "status":    "ok",
            "echo":      message,
            "user_name": user_name,
            "timestamp": ts,
            "note":      "EchoTool stub — no Lambda call made. Local stack verified.",
        }
