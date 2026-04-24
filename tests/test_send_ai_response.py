"""
Tests for the send_ai_response function in ai_handler.py

This module tests the message splitting functionality for various message lengths and formats.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import textwrap
from message_manager import send_ai_response, TypingIndicatorManager, clean_ai_response


def simulate_send_ai_response(text):
    """
    Simulate the send_ai_response function to generate expected results for testing
    """
    # Clean the text before processing
    text = clean_ai_response(text)
    
    # Split by paragraphs
    parts = text.split("\n\n")
    
    # Chunk long parts
    safe_parts = []
    for part in parts:
        chunks = textwrap.wrap(part, width=4000, break_long_words=False, break_on_hyphens=False)
        safe_parts.extend(chunks)
    
    return safe_parts


class TestSendAIResponse:
    """Test the send_ai_response function"""
    
    @pytest.mark.asyncio
    async def test_short_message_single_send(self):
        """Test that short messages (under 4000 characters) are sent as a single message"""
        # Create a short message
        short_message = "This is a short message that should be sent in one piece."
        assert len(short_message) < 4000
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=short_message, bot=mock_bot)
        
        # Verify the bot's send_message was called exactly once with the entire message
        mock_bot.send_message.assert_called_once_with(chat_id=123, text=short_message)
    
    @pytest.mark.asyncio
    async def test_long_message_multiple_sends(self):
        """Test that long messages (over 4000 characters) are split into multiple messages"""
        # Create a long message with multiple words that can be split
        long_message = "This is a long message with multiple words that should be split into multiple parts. " * 100
        assert len(long_message) > 4000
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=long_message, bot=mock_bot)
        
        # Generate expected results using our simulation
        expected_parts = simulate_send_ai_response(long_message)
        
        # Verify the bot's send_message was called the expected number of times
        assert mock_bot.send_message.call_count == len(expected_parts)
        
        # Verify each call was made with the expected text
        for i, expected_text in enumerate(expected_parts):
            # Get the args for this call
            call_args = mock_bot.send_message.call_args_list[i]
            args, kwargs = call_args
            assert kwargs['text'] == expected_text
    
    @pytest.mark.asyncio
    async def test_paragraph_splitting(self):
        """Test that messages with multiple paragraphs are split by paragraphs when possible"""
        # Create a message with multiple paragraphs
        paragraph1 = "This is the first paragraph.\nIt has multiple sentences."
        paragraph2 = "This is the second paragraph.\nIt also has multiple sentences."
        paragraph3 = "This is the third paragraph.\nIt is the last one."
        
        multi_paragraph_message = f"{paragraph1}\n\n{paragraph2}\n\n{paragraph3}"
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=multi_paragraph_message, bot=mock_bot)
        
        # Generate expected results using our simulation
        expected_parts = simulate_send_ai_response(multi_paragraph_message)
        
        # Verify the bot's send_message was called the expected number of times
        assert mock_bot.send_message.call_count == len(expected_parts)
        
        # Verify each call was made with the expected text
        for i, expected_text in enumerate(expected_parts):
            # Get the args for this call
            call_args = mock_bot.send_message.call_args_list[i]
            args, kwargs = call_args
            assert kwargs['text'] == expected_text
    
    @pytest.mark.asyncio
    async def test_long_paragraph_chunking(self):
        """Test that very long paragraphs are chunked appropriately without breaking words"""
        # Create a message with a very long paragraph (over 4000 characters)
        long_paragraph = "This is a very long paragraph without any paragraph breaks. " * 100
        assert len(long_paragraph) > 4000
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=long_paragraph, bot=mock_bot)
        
        # Generate expected results using our simulation
        expected_parts = simulate_send_ai_response(long_paragraph)
        
        # Verify the bot's send_message was called the expected number of times
        assert mock_bot.send_message.call_count == len(expected_parts)
        
        # Verify each call was made with the expected text
        for i, expected_text in enumerate(expected_parts):
            # Get the args for this call
            call_args = mock_bot.send_message.call_args_list[i]
            args, kwargs = call_args
            assert kwargs['text'] == expected_text
    
    @pytest.mark.asyncio
    async def test_exact_400_char_boundary(self):
        """Test behavior when message length is exactly at the 4000 character boundary"""
        # Create a message that is exactly 4000 characters
        exact_length_message = "A" * 4000
        assert len(exact_length_message) == 4000
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=exact_length_message, bot=mock_bot)
        
        # Generate expected results using our simulation
        expected_parts = simulate_send_ai_response(exact_length_message)
        
        # Verify the bot's send_message was called the expected number of times
        assert mock_bot.send_message.call_count == len(expected_parts)
        
        # Verify each call was made with the expected text
        for i, expected_text in enumerate(expected_parts):
            # Get the args for this call
            call_args = mock_bot.send_message.call_args_list[i]
            args, kwargs = call_args
            assert kwargs['text'] == expected_text
    
    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Test behavior with an empty message"""
        # Create an empty message
        empty_message = ""
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=empty_message, bot=mock_bot)
        
        # Generate expected results using our simulation
        expected_parts = simulate_send_ai_response(empty_message)
        
        # Verify the bot's send_message was called the expected number of times
        assert mock_bot.send_message.call_count == len(expected_parts)
        
        # Verify each call was made with the expected text
        for i, expected_text in enumerate(expected_parts):
            # Get the args for this call
            call_args = mock_bot.send_message.call_args_list[i]
            args, kwargs = call_args
            assert kwargs['text'] == expected_text

    @pytest.mark.asyncio
    async def test_clean_text_functionality(self):
        """Test that the clean_text function properly cleans the text"""
        # Create a message with extra whitespace and newlines
        dirty_message = "  \n\n  Hello world!  \n\n\n  This is a test.  \n\n  "
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=dirty_message, bot=mock_bot)
        
        # The expected cleaned text should have:
        # - Leading/trailing whitespace removed
        # - Multiple consecutive newlines reduced to double newlines
        # - Leading/trailing whitespace removed from each line
        # After splitting by "\n\n", we should get two parts
        expected_parts = ["Hello world!", "This is a test."]
        
        # Verify the bot's send_message was called twice with the cleaned message parts
        assert mock_bot.send_message.call_count == 2
        
        # Verify each call was made with the expected text
        for i, expected_text in enumerate(expected_parts):
            call_args = mock_bot.send_message.call_args_list[i]
            args, kwargs = call_args
            assert kwargs['text'] == expected_text

    @pytest.mark.asyncio
    async def test_message_with_only_paragraph_breaks(self):
        """Test behavior with a message containing only paragraph breaks"""
        # Create a message with only paragraph breaks
        paragraph_breaks_message = "\n\n\n"
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Call the function
        await send_ai_response(chat_id=123, text=paragraph_breaks_message, bot=mock_bot)
        
        # Generate expected results using our simulation
        expected_parts = simulate_send_ai_response(paragraph_breaks_message)
        
        # Verify the bot's send_message was called the expected number of times
        assert mock_bot.send_message.call_count == len(expected_parts)
        
        # Verify each call was made with the expected text
        for i, expected_text in enumerate(expected_parts):
            # Get the args for this call
            call_args = mock_bot.send_message.call_args_list[i]
            args, kwargs = call_args
            assert kwargs['text'] == expected_text


if __name__ == "__main__":
    pytest.main([__file__])