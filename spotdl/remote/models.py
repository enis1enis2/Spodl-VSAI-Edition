"""
Remote system models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

__all__ = [
    "OrderStatus",
    "ClientStatus",
    "DownloadOrder",
    "ClientInfo",
    "ServerStatus",
    "QueueStats",
]


class OrderStatus(str, Enum):
    """Status of a download order."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClientStatus(str, Enum):
    """Status of a remote client."""

    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"


class DownloadOrder(BaseModel):
    """Represents a download order from the server."""

    order_id: str = Field(..., description="Unique order ID")
    query: str = Field(..., description="Search query or URL to download")
    priority: int = Field(default=0, description="Priority level (higher = sooner)")
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    client_id: Optional[str] = Field(default=None, description="Assigned client ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_path: Optional[str] = None
    error: Optional[str] = None
    retries: int = Field(default=0)
    max_retries: int = Field(default=3)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "order_id": "ord_abc123",
                "query": "https://open.spotify.com/track/4vfN00PlILRXy5dcXHQE9M",
                "priority": 5,
                "status": "pending",
                "client_id": None,
                "created_at": "2026-09-07T10:00:00Z",
            }
        }


class ClientInfo(BaseModel):
    """Represents a connected remote client."""

    client_id: str
    status: ClientStatus = ClientStatus.ONLINE
    hostname: Optional[str] = None
    platform: Optional[str] = None
    current_order_id: Optional[str] = None
    completed_orders: int = 0
    failed_orders: int = 0
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    download_dir: Optional[str] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class ServerStatus(BaseModel):
    """Overall server status."""

    total_orders: int = 0
    pending_orders: int = 0
    completed_orders: int = 0
    failed_orders: int = 0
    active_clients: int = 0
    total_clients: int = 0


class QueueStats(BaseModel):
    """Queue statistics."""

    pending: int = 0
    assigned: int = 0
    downloading: int = 0
    completed: int = 0
    failed: int = 0
    total: int = 0
