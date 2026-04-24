"""
Performance tests for the buffering mechanism.

This module tests:
- High-concurrency scenarios
- Buffer cleanup functionality
- Memory usage with large numbers of buffered messages
"""

import pytest
import pytest_asyncio
import asyncio
import time
import gc
from unittest.mock import AsyncMock, Mock

from buffer_manager import BufferManager, UserBuffer


class TestBufferPerformance:
    """Test performance of buffering mechanism."""

    @pytest_asyncio.fixture
    async def buffer_manager(self):
        """Create a BufferManager instance for testing."""
        return BufferManager()

    @pytest.mark.asyncio
    async def test_high_concurrency_scenario(self, buffer_manager):
        """Test high-concurrency scenario with many users."""
        num_users = 10
        messages_per_user = 10
        
        # Create concurrent tasks for multiple users
        async def add_messages_for_user(user_id):
            for i in range(messages_per_user):
                await buffer_manager.add_message(user_id, f"User {user_id} message {i}")
        
        # Start all tasks concurrently
        start_time = time.time()
        tasks = [add_messages_for_user(user_id) for user_id in range(num_users)]
        await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Verify all messages were added
        for user_id in range(num_users):
            size = await buffer_manager.get_buffer_size(user_id)
            assert size == messages_per_user
        
        # Log performance metrics
        total_messages = num_users * messages_per_user
        duration = end_time - start_time
        rate = total_messages / duration if duration > 0 else 0
        
        print(f"Added {total_messages} messages in {duration:.4f} seconds ({rate:.2f} messages/second)")

    @pytest.mark.asyncio
    async def test_buffer_cleanup_performance(self, buffer_manager):
        """Test performance of buffer cleanup functionality."""
        num_users = 500
        
        # Create many user buffers
        for user_id in range(num_users):
            await buffer_manager.add_message(user_id, f"Message for user {user_id}")
        
        # Verify all buffers exist
        active_buffers = len(buffer_manager.user_buffers)
        assert active_buffers == num_users
        
        # Make half of them inactive
        cutoff_time = time.time() - 1000  # 1000 seconds ago
        for user_id in range(0, num_users, 2):  # Every other user
            buffer = buffer_manager.get_user_buffer(user_id)
            buffer.last_activity = cutoff_time
        
        # Measure cleanup performance
        start_time = time.time()
        await buffer_manager.cleanup_inactive_buffers(max_age_seconds=500)
        end_time = time.time()
        
        # Verify cleanup worked
        remaining_buffers = len(buffer_manager.user_buffers)
        assert remaining_buffers == num_users // 2  # Half should remain
        
        # Log performance
        cleanup_duration = end_time - start_time
        print(f"Cleaned up {num_users // 2} inactive buffers in {cleanup_duration:.4f} seconds")

    @pytest.mark.asyncio
    async def test_memory_usage_with_large_messages(self, buffer_manager):
        """Test memory usage with large numbers of buffered messages."""
        user_id = 12345
        num_messages = 1000
        message_size = 100  # 1000 characters per message
        
        # Create large messages
        large_message = "A" * message_size
        
        # Add many large messages
        start_time = time.time()
        for i in range(num_messages):
            await buffer_manager.add_message(user_id, f"{large_message} {i}")
        end_time = time.time()
        
        # Verify messages were added
        buffer_size = await buffer_manager.get_buffer_size(user_id)
        assert buffer_size == num_messages
        
        # Get concatenated message
        concatenated = await buffer_manager.get_user_buffer(user_id).get_concatenated_message()
        expected_length = (message_size + 1) * num_messages + (num_messages - 1)  # +1 for space, -1 for last space
        assert len(concatenated) >= expected_length
        
        # Log performance
        duration = end_time - start_time
        total_chars = num_messages * (message_size + 1)  # +1 for space
        print(f"Added {num_messages} large messages ({total_chars} chars) in {duration:.4f} seconds")

    @pytest.mark.asyncio
    async def test_concurrent_dispatch_scheduling(self, buffer_manager):
        """Test performance of concurrent dispatch scheduling."""
        num_users = 50
        dispatch_calls = {}
        events = {}
        
        # Create dispatch functions that track calls
        for user_id in range(num_users):
            events[user_id] = asyncio.Event()
            dispatch_calls[user_id] = 0
        
        async def mock_dispatch_func(user_id):
            dispatch_calls[user_id] += 1
            events[user_id].set()
        
        # Add messages for all users
        for user_id in range(num_users):
            await buffer_manager.add_message(user_id, f"Message for user {user_id}")
        
        # Schedule dispatch for all users concurrently
        start_time = time.time()
        tasks = [
            buffer_manager.schedule_dispatch(user_id, mock_dispatch_func)
            for user_id in range(num_users)
        ]
        await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Wait for all dispatches to complete
        wait_tasks = [events[user_id].wait() for user_id in range(num_users)]
        try:
            await asyncio.wait_for(asyncio.gather(*wait_tasks), timeout=10.0)
        except asyncio.TimeoutError:
            pytest.fail("Not all dispatch functions were called within timeout")
        
        # Verify all dispatch functions were called exactly once
        for user_id in range(num_users):
            assert dispatch_calls[user_id] == 1
        
        # Log performance
        duration = end_time - start_time
        rate = num_users / duration if duration > 0 else 0
        print(f"Scheduled {num_users} dispatches in {duration:.4f} seconds ({rate:.2f} dispatches/second)")

    @pytest.mark.asyncio
    async def test_buffer_memory_pressure(self, buffer_manager):
        """Test buffer behavior under memory pressure."""
        user_id = 12345
        num_messages = 10000
        message_pattern = "This is a test message with some content to simulate real usage "
        
        # Add a large number of messages
        start_time = time.time()
        for i in range(num_messages):
            await buffer_manager.add_message(user_id, f"{message_pattern}{i}")
        add_duration = time.time() - start_time
        
        # Check memory usage before dispatch
        buffer = buffer_manager.get_user_buffer(user_id)
        messages = await buffer.get_messages()
        assert len(messages) == num_messages
        
        # Dispatch buffer
        start_time = time.time()
        result = await buffer_manager.dispatch_buffer(user_id)
        dispatch_duration = time.time() - start_time
        
        # Verify result
        assert result is not None
        assert len(result) > 0
        
        # Verify buffer is now empty
        assert await buffer.is_empty()
        
        # Log performance
        print(f"Added {num_messages} messages in {add_duration:.4f} seconds")
        print(f"Dispatched buffer in {dispatch_duration:.4f} seconds")
        print(f"Average time per message addition: {add_duration/num_messages*1000:.4f} ms")

    @pytest.mark.asyncio
    async def test_concurrent_buffer_operations_performance(self, buffer_manager):
        """Test performance of concurrent buffer operations."""
        num_users = 200
        operations_per_user = 50
        
        # Define operations
        async def user_operations(user_id):
            for i in range(operations_per_user):
                # Mix of operations
                if i % 3 == 0:
                    # Add message
                    await buffer_manager.add_message(user_id, f"User {user_id} message {i}")
                elif i % 3 == 1:
                    # Get buffer size
                    await buffer_manager.get_buffer_size(user_id)
                else:
                    # Get user buffer
                    buffer_manager.get_user_buffer(user_id)
        
        # Run concurrent operations
        start_time = time.time()
        tasks = [user_operations(user_id) for user_id in range(num_users)]
        await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Log performance
        total_operations = num_users * operations_per_user
        duration = end_time - start_time
        rate = total_operations / duration if duration > 0 else 0
        
        print(f"Completed {total_operations} mixed operations in {duration:.4f} seconds ({rate:.2f} ops/second)")

    @pytest.mark.asyncio
    async def test_buffer_cleanup_with_many_inactive_buffers(self, buffer_manager):
        """Test cleanup performance with many inactive buffers."""
        num_active = 10
        num_inactive = 900
        total_buffers = num_active + num_inactive
        
        # Create active buffers
        for user_id in range(num_active):
            await buffer_manager.add_message(user_id, f"Active message {user_id}")
        
        # Create inactive buffers with old timestamps
        cutoff_time = time.time() - 10000  # 1000 seconds ago
        for user_id in range(num_active, total_buffers):
            await buffer_manager.add_message(user_id, f"Inactive message {user_id}")
            buffer = buffer_manager.get_user_buffer(user_id)
            buffer.last_activity = cutoff_time
        
        # Verify setup
        assert len(buffer_manager.user_buffers) == total_buffers
        
        # Measure cleanup performance
        start_time = time.time()
        await buffer_manager.cleanup_inactive_buffers(max_age_seconds=5000)
        end_time = time.time()
        
        # Verify results
        assert len(buffer_manager.user_buffers) == num_active
        
        # Log performance
        cleanup_duration = end_time - start_time
        print(f"Cleaned up {num_inactive} inactive buffers in {cleanup_duration:.4f} seconds")

    @pytest.mark.asyncio
    async def test_user_buffer_memory_efficiency(self):
        """Test memory efficiency of UserBuffer instances."""
        num_buffers = 10000
        buffers = []
        
        # Create many UserBuffer instances
        start_time = time.time()
        for i in range(num_buffers):
            buffer = UserBuffer(user_id=i)
            buffers.append(buffer)
        create_duration = time.time() - start_time
        
        # Add messages to some buffers
        start_time = time.time()
        for i in range(0, num_buffers, 100):  # Every 100th buffer
            await buffers[i].add_message(f"Test message for buffer {i}")
        add_duration = time.time() - start_time
        
        # Verify some buffers have messages
        non_empty_count = 0
        for i in range(0, num_buffers, 100):
            if not await buffers[i].is_empty():
                non_empty_count += 1
        
        expected_non_empty = num_buffers // 100
        assert non_empty_count == expected_non_empty
        
        # Log performance
        print(f"Created {num_buffers} UserBuffer instances in {create_duration:.4f} seconds")
        print(f"Added messages to {non_empty_count} buffers in {add_duration:.4f} seconds")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_long_running_buffer_operations(self, buffer_manager):
        """Test buffer operations over a longer period."""
        user_id = 12345
        duration_seconds = 30
        end_time = time.time() + duration_seconds
        
        operations_count = 0
        
        # Run mixed operations for the specified duration
        while time.time() < end_time:
            # Add message
            await buffer_manager.add_message(user_id, f"Message {operations_count}")
            operations_count += 1
            
            # Get buffer size occasionally
            if operations_count % 10 == 0:
                await buffer_manager.get_buffer_size(user_id)
                operations_count += 1
            
            # Dispatch buffer occasionally
            if operations_count % 50 == 0:
                await buffer_manager.dispatch_buffer(user_id)
                operations_count += 1
            
            # Small delay to prevent overwhelming the system
            await asyncio.sleep(0.001)  # 1ms delay
        
        # Final dispatch
        final_result = await buffer_manager.dispatch_buffer(user_id)
        
        # Log results
        print(f"Performed {operations_count} operations in {duration_seconds} seconds")
        print(f"Average operations per second: {operations_count/duration_seconds:.2f}")
        print(f"Final buffer dispatch result length: {len(final_result) if final_result else 0}")

    @pytest.mark.asyncio
    async def test_buffer_manager_scalability(self, buffer_manager):
        """Test scalability of BufferManager with increasing load."""
        # Test with increasing numbers of users
        user_counts = [10, 50, 100, 500]
        
        for user_count in user_counts:
            # Reset for each test
            buffer_manager.user_buffers.clear()
            
            # Add messages for all users
            start_time = time.time()
            for user_id in range(user_count):
                await buffer_manager.add_message(user_id, f"Message for user {user_id}")
            add_duration = time.time() - start_time
            
            # Verify all users have buffers
            assert len(buffer_manager.user_buffers) == user_count
            
            # Get buffer sizes for all users
            start_time = time.time()
            sizes = []
            for user_id in range(user_count):
                size = await buffer_manager.get_buffer_size(user_id)
                sizes.append(size)
            get_duration = time.time() - start_time
            
            # Verify all sizes are correct
            assert all(size == 1 for size in sizes)
            
            # Log performance for this user count
            print(f"{user_count} users: {add_duration:.4f}s to add, {get_duration:.4f}s to query")