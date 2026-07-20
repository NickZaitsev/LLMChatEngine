"""The messaging package split must preserve the legacy import surface.

``message_manager`` is a compatibility re-export shim; every public name it
exposed historically must resolve to the same object as its new home in the
``messaging`` package.
"""

import message_manager
import messaging
from messaging import dispatcher, formatting, queue, sending, typing


def test_message_manager_reexports_are_identical_objects():
    assert message_manager.clean_ai_response is formatting.clean_ai_response
    assert message_manager._split_ai_response is formatting._split_ai_response
    assert message_manager.TypingIndicatorManager is typing.TypingIndicatorManager
    assert message_manager.MessageQueueManager is queue.MessageQueueManager
    assert message_manager.MessageDispatcher is dispatcher.MessageDispatcher
    assert message_manager.send_ai_response is sending.send_ai_response
    assert message_manager.generate_ai_response is sending.generate_ai_response


def test_package_namespace_reexports_match_submodules():
    assert messaging.MessageDispatcher is dispatcher.MessageDispatcher
    assert messaging.MessageQueueManager is queue.MessageQueueManager
    assert messaging.TypingIndicatorManager is typing.TypingIndicatorManager
    assert messaging.send_ai_response is sending.send_ai_response


def test_legacy_patch_attributes_still_exist_on_shim():
    # Tools and older tests patch these attributes through message_manager.
    assert hasattr(message_manager, "redis_async")
    assert hasattr(message_manager, "Bot")
    assert hasattr(message_manager, "TELEGRAM_TOKEN")
