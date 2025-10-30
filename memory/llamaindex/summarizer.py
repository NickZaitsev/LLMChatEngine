"""
LlamaIndex summarizer implementation.

This module provides the `LlamaIndexSummarizer` class, which implements the
`SummarizationModel` abstraction using the `AIHandler` to generate summaries.
"""

from typing import Optional
from core.abstractions import SummarizationModel as SummarizationModelAbstraction
from ai_handler import AIHandler

class LlamaIndexSummarizer(SummarizationModelAbstraction):
    """
    LlamaIndexSummarizer implementation.
    """

    def __init__(self, ai_handler: AIHandler):
        """
        Initialize the LlamaIndexSummarizer.

        Args:
            ai_handler: The AI handler to use for generating summaries.
        """
        self._ai_handler = ai_handler

    async def summarize(self, text: str, prompt_template: str, user_id: Optional[str] = None) -> str:
        """
        Summarize a piece of text.

        Args:
            text: The text to summarize.
            prompt_template: The prompt template to use for summarization.
            user_id: The optional ID of the user.

        Returns:
            The summarized text.
        """
        prompt = prompt_template.format(text=text)
        # Use direct AI request without conversation context for summarization
        return await self._ai_handler._make_ai_request([{"role": "user", "content": prompt}])