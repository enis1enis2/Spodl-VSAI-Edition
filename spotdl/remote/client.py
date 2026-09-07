"""
Remote client module.
Connects to a spotDL remote server and processes download orders.
"""

import asyncio
import json
import logging
import platform
import socket
from typing import Any, Dict, Optional

import websockets
from websockets.client import WebSocketClientProtocol

from spotdl.download.downloader import Downloader
from spotdl.types.options import DownloaderOptions
from spotdl.utils.config import DOWNLOADER_OPTIONS, create_settings_type

__all__ = ["RemoteClient"]

logger = logging.getLogger(__name__)


class RemoteClient:
    """
    Remote client that connects to a spotDL remote server,
    receives download orders, and processes them.
    """

    def __init__(
        self,
        server_url: str,
        downloader_settings: Optional[DownloaderOptions] = None,
        download_dir: Optional[str] = None,
        heartbeat_interval: int = 30,
    ):
        self.server_url = server_url.rstrip("/")
        self.downloader_settings = downloader_settings or self._default_settings()
        self.download_dir = download_dir
        self.heartbeat_interval = heartbeat_interval
        self.client_id: Optional[str] = None
        self.ws: Optional[WebSocketClientProtocol] = None
        self._running = False
        self._downloader: Optional[Downloader] = None

    def _default_settings(self) -> DownloaderOptions:
        return DownloaderOptions(
            **create_settings_type(
                __import__("argparse").Namespace(config=False),
                {},
                DOWNLOADER_OPTIONS,
            )
        )

    def _get_hostname(self) -> str:
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    async def connect(self) -> None:
        """Connect to the remote server."""
        ws_url = self.server_url.replace("http", "ws") + "/ws/client"
        logger.info("Connecting to server: %s", ws_url)

        self.ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)

        registration = {
            "type": "register",
            "hostname": self._get_hostname(),
            "platform": platform.system(),
            "download_dir": self.download_dir,
            "capabilities": {
                "formats": ["mp3", "m4a", "opus", "flac"],
                "audio_providers": list(
                    self.downloader_settings.get("audio_providers", [])
                ),
            },
        }
        await self.ws.send(json.dumps(registration))

        response = await self.ws.recv()
        data = json.loads(response)
        self.client_id = data.get("client_id")
        logger.info("Connected to server, client ID: %s", self.client_id)

    async def start(self) -> None:
        """Start the client main loop."""
        if not self.ws:
            await self.connect()

        self._running = True
        self._downloader = Downloader(settings=self.downloader_settings)

        orders_ws_url = (
            self.server_url.replace("http", "ws") + "/ws/client/orders"
        )
        async with websockets.connect(
            orders_ws_url, max_size=50 * 1024 * 1024
        ) as orders_ws:
            registration = {"type": "register", "client_id": self.client_id}
            await orders_ws.send(json.dumps(registration))

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(orders_ws))

            try:
                while self._running:
                    try:
                        message = await asyncio.wait_for(
                            orders_ws.recv(), timeout=1
                        )
                        data = json.loads(message)
                        await self._handle_message(orders_ws, data)
                    except asyncio.TimeoutError:
                        continue
            except websockets.exceptions.ConnectionClosed:
                logger.info("Connection closed by server")
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self, ws: WebSocketClientProtocol) -> None:
        """Send periodic heartbeats."""
        while self._running:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                await ws.send(
                    json.dumps(
                        {"type": "heartbeat", "client_id": self.client_id}
                    )
                )
            except Exception:
                break

    async def _handle_message(
        self,
        ws: WebSocketClientProtocol,
        data: Dict[str, Any],
    ) -> None:
        """Handle incoming message from server."""
        msg_type = data.get("type")

        if msg_type == "order":
            order_data = data.get("order", {})
            await self._process_order(ws, order_data)

    async def _process_order(
        self,
        ws: WebSocketClientProtocol,
        order_data: Dict[str, Any],
    ) -> None:
        """Process a download order."""
        order_id = order_data.get("order_id")
        query = order_data.get("query")
        logger.info("Processing order %s: %s", order_id, query)

        try:
            if self.download_dir:
                self.downloader_settings["output"] = self.download_dir

            from spotdl.types.song import Song
            song = Song.from_search_term(query)
            _, path = await self._downloader.pool_download(song)

            if path:
                await ws.send(json.dumps({
                    "type": "order_complete",
                    "order_id": order_id,
                    "result_path": str(path.absolute()),
                }))
                logger.info("Order %s completed: %s", order_id, path)
            else:
                await ws.send(json.dumps({
                    "type": "order_failed",
                    "order_id": order_id,
                    "error": "Download returned no path",
                }))

        except Exception as exc:
            logger.error("Order %s failed: %s", order_id, exc)
            await ws.send(json.dumps({
                "type": "order_failed",
                "order_id": order_id,
                "error": str(exc),
            }))

    def stop(self) -> None:
        """Stop the client."""
        self._running = False
