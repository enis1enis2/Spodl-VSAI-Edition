"""
Remote client/server module for distributed downloads.
"""

from spotdl.remote.client import RemoteClient
from spotdl.remote.models import (
    ClientInfo,
    ClientStatus,
    DownloadOrder,
    OrderStatus,
    QueueStats,
    ServerStatus,
)
from spotdl.remote.queue import DownloadQueue
from spotdl.remote.server import RemoteServer, create_app

__all__ = [
    "RemoteClient",
    "RemoteServer",
    "create_app",
    "DownloadQueue",
    "ClientInfo",
    "ClientStatus",
    "DownloadOrder",
    "OrderStatus",
    "QueueStats",
    "ServerStatus",
]
