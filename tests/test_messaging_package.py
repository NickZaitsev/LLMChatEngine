"""The ``messaging`` package is the single public import surface.

The historical ``message_manager`` re-export shim has been retired; new and
existing code must import from the ``messaging`` package (or its submodules).
"""

import importlib

import pytest

import messaging
from messaging import dispatcher, formatting, queue, sending, typing


def test_message_manager_shim_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("message_manager")


def test_package_namespace_reexports_match_submodules():
    assert messaging.MessageDispatcher is dispatcher.MessageDispatcher
    assert messaging.MessageQueueManager is queue.MessageQueueManager
    assert messaging.TypingIndicatorManager is typing.TypingIndicatorManager
    assert messaging.send_ai_response is sending.send_ai_response
    assert messaging.generate_ai_response is sending.generate_ai_response
    assert messaging.clean_ai_response is formatting.clean_ai_response
