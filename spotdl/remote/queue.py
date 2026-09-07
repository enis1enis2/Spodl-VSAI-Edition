"""
Download queue system for remote client/server architecture.
"""

import heapq
import logging
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from spotdl.remote.models import DownloadOrder, OrderStatus

__all__ = ["DownloadQueue"]

logger = logging.getLogger(__name__)


class DownloadQueue:
    """
    Priority-based download queue for the remote system.
    Supports priority levels, client assignment, and retry logic.
    """

    def __init__(self):
        self._queue: List[tuple] = []  # Min-heap: (-priority, order_id, order)
        self._orders: Dict[str, DownloadOrder] = {}
        self._lock = threading.Lock()
        self._order_counter = 0

    def _next_order_id(self) -> str:
        return f"ord_{uuid.uuid4().hex[:8]}"

    def enqueue(
        self,
        query: str,
        priority: int = 0,
        max_retries: int = 3,
    ) -> DownloadOrder:
        """
        Add a new download order to the queue.

        ### Arguments
        - query: The search query or URL.
        - priority: Priority level (higher = sooner).
        - max_retries: Maximum retry attempts.

        ### Returns
        - The created DownloadOrder.
        """
        with self._lock:
            order_id = self._next_order_id()
            order = DownloadOrder(
                order_id=order_id,
                query=query,
                priority=priority,
                max_retries=max_retries,
            )
            self._orders[order_id] = order
            self._order_counter += 1
            heapq.heappush(self._queue, (-priority, self._order_counter, order_id))
            logger.info("Order enqueued: %s (priority=%d)", order_id, priority)
            return order

    def dequeue(self) -> Optional[DownloadOrder]:
        """
        Get the highest-priority pending order.

        ### Returns
        - The next DownloadOrder, or None if queue is empty.
        """
        with self._lock:
            while self._queue:
                _, _, order_id = heapq.heappop(self._queue)
                order = self._orders.get(order_id)
                if order and order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.ASSIGNED
                    order.assigned_at = datetime.utcnow()
                    return order
            return None

    def get_order(self, order_id: str) -> Optional[DownloadOrder]:
        """Get an order by ID."""
        return self._orders.get(order_id)

    def assign(self, order_id: str, client_id: str) -> bool:
        """
        Assign an order to a client.

        ### Returns
        - True if assignment succeeded.
        """
        with self._lock:
            order = self._orders.get(order_id)
            if order and order.status in (OrderStatus.PENDING, OrderStatus.ASSIGNED):
                order.client_id = client_id
                order.status = OrderStatus.DOWNLOADING
                order.assigned_at = datetime.utcnow()
                logger.info("Order %s assigned to client %s", order_id, client_id)
                return True
            return False

    def complete(self, order_id: str, result_path: Optional[str] = None) -> bool:
        """
        Mark an order as completed.

        ### Returns
        - True if completion succeeded.
        """
        with self._lock:
            order = self._orders.get(order_id)
            if order:
                order.status = OrderStatus.COMPLETED
                order.completed_at = datetime.utcnow()
                order.result_path = result_path
                logger.info("Order %s completed", order_id)
                return True
            return False

    def fail(self, order_id: str, error: str) -> bool:
        """
        Mark an order as failed, with retry logic.

        ### Returns
        - True if failed, False if retrying.
        """
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return False

            order.retries += 1
            if order.retries < order.max_retries:
                order.status = OrderStatus.PENDING
                order.error = error
                order.client_id = None
                order.assigned_at = None
                self._order_counter += 1
                heapq.heappush(
                    self._queue, (-order.priority, self._order_counter, order_id)
                )
                logger.warning(
                    "Order %s failed, retrying (%d/%d): %s",
                    order_id,
                    order.retries,
                    order.max_retries,
                    error,
                )
                return False

            order.status = OrderStatus.FAILED
            order.completed_at = datetime.utcnow()
            order.error = error
            logger.error("Order %s permanently failed: %s", order_id, error)
            return True

    def cancel(self, order_id: str) -> bool:
        """Cancel an order."""
        with self._lock:
            order = self._orders.get(order_id)
            if order and order.status in (
                OrderStatus.PENDING,
                OrderStatus.ASSIGNED,
            ):
                order.status = OrderStatus.CANCELLED
                order.completed_at = datetime.utcnow()
                logger.info("Order %s cancelled", order_id)
                return True
            return False

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        with self._lock:
            stats = {status.value: 0 for status in OrderStatus}
            for order in self._orders.values():
                stats[order.status.value] += 1
            stats["total"] = len(self._orders)
            return stats

    def list_orders(
        self,
        status: Optional[OrderStatus] = None,
        client_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[DownloadOrder]:
        """
        List orders, optionally filtered.

        ### Arguments
        - status: Filter by status.
        - client_id: Filter by assigned client.
        - limit: Maximum number of results.

        ### Returns
        - List of matching DownloadOrders.
        """
        with self._lock:
            results = list(self._orders.values())

        if status:
            results = [o for o in results if o.status == status]
        if client_id:
            results = [o for o in results if o.client_id == client_id]

        results.sort(key=lambda o: o.created_at, reverse=True)
        return results[:limit]

    def all_orders(self) -> List[DownloadOrder]:
        """Get all orders."""
        with self._lock:
            return list(self._orders.values())
