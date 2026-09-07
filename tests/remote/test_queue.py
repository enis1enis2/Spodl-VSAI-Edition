"""
Tests for the remote module.
"""

import pytest

from spotdl.remote.models import (
    ClientInfo,
    ClientStatus,
    DownloadOrder,
    OrderStatus,
    QueueStats,
)
from spotdl.remote.queue import DownloadQueue


class TestDownloadQueue:
    """Tests for DownloadQueue."""

    def test_enqueue_and_dequeue(self):
        """Test basic enqueue and dequeue."""
        queue = DownloadQueue()

        order1 = queue.enqueue("song1", priority=1)
        order2 = queue.enqueue("song2", priority=2)
        order3 = queue.enqueue("song3", priority=0)

        assert order1.status == OrderStatus.PENDING
        assert order2.status == OrderStatus.PENDING
        assert order3.status == OrderStatus.PENDING

        first = queue.dequeue()
        assert first is not None
        assert first.query == "song2"
        assert first.status == OrderStatus.ASSIGNED

    def test_priority_ordering(self):
        """Test that higher priority items are dequeued first."""
        queue = DownloadQueue()

        queue.enqueue("low", priority=1)
        queue.enqueue("high", priority=10)
        queue.enqueue("medium", priority=5)

        first = queue.dequeue()
        assert first.query == "high"

        second = queue.dequeue()
        assert second.query == "medium"

        third = queue.dequeue()
        assert third.query == "low"

    def test_assign_and_complete(self):
        """Test assign and complete flow."""
        queue = DownloadQueue()

        order = queue.enqueue("song")
        queue.assign(order.order_id, "client1")

        assert order.status == OrderStatus.DOWNLOADING
        assert order.client_id == "client1"

        queue.complete(order.order_id, "/path/to/file.mp3")
        assert order.status == OrderStatus.COMPLETED
        assert order.result_path == "/path/to/file.mp3"

    def test_fail_with_retry(self):
        """Test fail with retry logic."""
        queue = DownloadQueue()

        order = queue.enqueue("song", max_retries=3)

        queue.assign(order.order_id, "client1")
        result = queue.fail(order.order_id, "Network error")

        assert not result
        assert order.status == OrderStatus.PENDING
        assert order.retries == 1

        queue.assign(order.order_id, "client1")
        result = queue.fail(order.order_id, "Network error again")
        assert not result
        assert order.retries == 2

        queue.assign(order.order_id, "client1")
        result = queue.fail(order.order_id, "Permanent failure")
        assert result
        assert order.status == OrderStatus.FAILED

    def test_cancel(self):
        """Test cancel."""
        queue = DownloadQueue()

        order = queue.enqueue("song")
        result = queue.cancel(order.order_id)
        assert result
        assert order.status == OrderStatus.CANCELLED

    def test_get_stats(self):
        """Test get stats."""
        queue = DownloadQueue()

        queue.enqueue("song1")
        order2 = queue.enqueue("song2")
        queue.assign(order2.order_id, "client1")
        queue.complete(order2.order_id, "/path/to/file.mp3")

        stats = queue.get_stats()
        assert stats["pending"] == 1
        assert stats["completed"] == 1
        assert stats["total"] == 2


class TestClientInfo:
    """Tests for ClientInfo model."""

    def test_client_info_creation(self):
        """Test creating a ClientInfo."""
        client = ClientInfo(
            client_id="client1",
            hostname="myhost",
            platform="Windows",
            download_dir="/downloads",
        )
        assert client.client_id == "client1"
        assert client.status == ClientStatus.ONLINE
        assert client.completed_orders == 0


class TestDownloadOrder:
    """Tests for DownloadOrder model."""

    def test_order_creation(self):
        """Test creating a DownloadOrder."""
        order = DownloadOrder(
            order_id="ord_123",
            query="test song",
            priority=5,
        )
        assert order.status == OrderStatus.PENDING
        assert order.retries == 0
