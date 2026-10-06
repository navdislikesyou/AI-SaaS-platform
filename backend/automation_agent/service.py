"""Service layer for the Automation Agent.

Wraps :class:`automation_agent.automation_agent.AutomationAgent` in a dict-in,
dict-out interface. The agent already separates parsing, recipient lookup,
and drafting; only :meth:`AutomationAgent.execute` needs translating, since it
returns a three-tuple.

``generate_email`` drafts. Nothing here sends mail.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from automation_agent.automation_agent import AutomationAgent
from automation_agent.llm.local_llm import LocalLLM

logger = logging.getLogger(__name__)


class AutomationService:
    """Dict-in, dict-out facade over the Automation Agent.

    The service owns no parsing or drafting logic of its own. It translates
    the agent's tuple return into the dictionary the API layer expects.
    """

    def __init__(self, settings: Settings) -> None:
        """Load the LLM client and employee directory once.

        Args:
            settings: Application settings supplying the Ollama model and base
                URL. The employee directory defaults to the packaged JSON file.

        Raises:
            Exception: Whatever the Ollama client or employee file read
                raises at construction. Construction is deliberately eager so
                that a misconfigured model surfaces here rather than on first
                use.
        """
        self._settings = settings

        self._agent = AutomationAgent(
            llm=LocalLLM(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
            ),
        )

        logger.info(
            "automation_service_ready model=%s employees=%d",
            settings.ollama_model,
            len(self._agent.employees),
        )

    def execute(self, instruction: str) -> dict[str, Any]:
        """Turn a natural language instruction into a meeting and a draft.

        Args:
            instruction: The instruction to act on, for example "Schedule a
                sprint planning on 5 March at 10 AM with Navneet".

        Returns:
            A dictionary with ``meeting`` holding the parsed details,
            ``recipients`` holding the matched employee records, and ``email``
            holding the drafted body. The draft is not sent.
        """
        meeting, recipients, email = self._agent.execute(instruction)

        logger.info(
            "automation_execute recipients=%d title=%s",
            len(recipients),
            meeting.get("title", ""),
        )

        return {
            "meeting": meeting,
            "recipients": recipients,
            "email": email,
        }
