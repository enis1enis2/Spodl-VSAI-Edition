"""
Remote server module.
FastAPI-based server for managing download clients and orders.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from spotdl.remote.models import ClientInfo, ClientStatus, DownloadOrder, OrderStatus
from spotdl.remote.queue import DownloadQueue
from spotdl.types.options import DownloaderOptions
from spotdl.utils.config import DOWNLOADER_OPTIONS, create_settings_type

__all__ = ["create_app", "RemoteServer"]

logger = logging.getLogger(__name__)


class RemoteServer:
    """
    Remote download server that manages clients and orders.
    """

    def __init__(
        self,
        downloader_settings: Optional[DownloaderOptions] = None,
        host: str = "0.0.0.0",
        port: int = 8801,
    ):
        self.host = host
        self.port = port
        self.queue = DownloadQueue()
        self.clients: Dict[str, ClientInfo] = {}
        self.downloader_settings = downloader_settings or self._default_settings()
        self.app = create_app(self)

    def _default_settings(self) -> DownloaderOptions:
        return DownloaderOptions(
            **create_settings_type(
                __import__("argparse").Namespace(config=False),
                {},
                DOWNLOADER_OPTIONS,
            )
        )

    def register_client(self, client_info: ClientInfo) -> None:
        """Register a new client."""
        self.clients[client_info.client_id] = client_info
        logger.info(
            "Client registered: %s (%s)",
            client_info.client_id,
            client_info.hostname,
        )

    def unregister_client(self, client_id: str) -> None:
        """Unregister a client."""
        if client_id in self.clients:
            del self.clients[client_id]
            logger.info("Client unregistered: %s", client_id)

    def get_client(self, client_id: str) -> Optional[ClientInfo]:
        """Get client info by ID."""
        return self.clients.get(client_id)

    def heartbeat(self, client_id: str) -> bool:
        """Update client heartbeat."""
        client = self.clients.get(client_id)
        if client:
            client.last_heartbeat = datetime.utcnow()
            return True
        return False

    def assign_order(self, order: DownloadOrder, client_id: str) -> bool:
        """Assign an order to a client."""
        client = self.clients.get(client_id)
        if not client:
            return False
        client.current_order_id = order.order_id
        client.status = ClientStatus.BUSY
        return self.queue.assign(order.order_id, client_id)

    def complete_order(
        self,
        order_id: str,
        client_id: str,
        result_path: Optional[str] = None,
    ) -> bool:
        """Mark an order as completed."""
        success = self.queue.complete(order_id, result_path)
        if success:
            client = self.clients.get(client_id)
            if client:
                client.current_order_id = None
                client.status = ClientStatus.ONLINE
                client.completed_orders += 1
        return success

    def fail_order(self, order_id: str, client_id: str, error: str) -> bool:
        """Mark an order as failed."""
        permanently_failed = self.queue.fail(order_id, error)
        if permanently_failed:
            client = self.clients.get(client_id)
            if client:
                client.current_order_id = None
                client.status = ClientStatus.ONLINE
                client.failed_orders += 1
        return permanently_failed

    def get_next_order(self) -> Optional[DownloadOrder]:
        """Get the next pending order."""
        return self.queue.dequeue()

    def get_stats(self) -> Dict:
        """Get server statistics."""
        queue_stats = self.queue.get_stats()
        active_clients = sum(
            1 for c in self.clients.values()
            if c.status != ClientStatus.OFFLINE
        )
        return {
            "queue": queue_stats,
            "clients": {
                "total": len(self.clients),
                "active": active_clients,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }


def create_app(server: RemoteServer) -> FastAPI:
    """Create the FastAPI application for the remote server."""
    app = FastAPI(
        title="spotDL Remote",
        description="Remote download management server for spotDL",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def index():
        return {"message": "spotDL Remote Server", "docs": "/docs"}

    @app.get("/api/status")
    async def get_status():
        return server.get_stats()

    @app.get("/api/orders")
    async def list_orders(status: Optional[str] = None, limit: int = 100):
        order_status = OrderStatus(status) if status else None
        orders = server.queue.list_orders(status=order_status, limit=limit)
        return [order.model_dump(mode="json") for order in orders]

    @app.post("/api/orders")
    async def create_order(query: str, priority: int = 0):
        order = server.queue.enqueue(query, priority=priority)
        return order.model_dump(mode="json")

    @app.get("/api/orders/{order_id}")
    async def get_order(order_id: str):
        order = server.queue.get_order(order_id)
        if not order:
            return JSONResponse(status_code=404, content={"error": "Order not found"})
        return order.model_dump(mode="json")

    @app.delete("/api/orders/{order_id}")
    async def cancel_order(order_id: str):
        success = server.queue.cancel(order_id)
        if not success:
            return JSONResponse(
                status_code=400,
                content={"error": "Cannot cancel order"},
            )
        return {"status": "cancelled"}

    @app.get("/api/clients")
    async def list_clients():
        return [client.model_dump(mode="json") for client in server.clients.values()]

    @app.get("/api/clients/{client_id}")
    async def get_client(client_id: str):
        client = server.get_client(client_id)
        if not client:
            return JSONResponse(status_code=404, content={"error": "Client not found"})
        return client.model_dump(mode="json")

    @app.websocket("/ws/client")
    async def websocket_client(websocket: WebSocket):
        await websocket.accept()
        client_id = str(uuid.uuid4())

        try:
            data = await websocket.receive_json()
            client_info = ClientInfo(
                client_id=client_id,
                hostname=data.get("hostname"),
                platform=data.get("platform"),
                download_dir=data.get("download_dir"),
                capabilities=data.get("capabilities", {}),
            )
            server.register_client(client_info)

            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(), timeout=30
                    )
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
                    continue

                msg_type = message.get("type")

                if msg_type == "heartbeat":
                    server.heartbeat(client_id)
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "order_complete":
                    order_id = message.get("order_id")
                    result_path = message.get("result_path")
                    server.complete_order(order_id, client_id, result_path)
                    await websocket.send_json({"type": "ack", "order_id": order_id})

                elif msg_type == "order_failed":
                    order_id = message.get("order_id")
                    error = message.get("error", "Unknown error")
                    server.fail_order(order_id, client_id, error)
                    await websocket.send_json({"type": "ack", "order_id": order_id})

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.error("WebSocket error: %s", exc)
        finally:
            server.unregister_client(client_id)

    @app.websocket("/ws/client/orders")
    async def websocket_client_orders(websocket: WebSocket):
        await websocket.accept()

        try:
            data = await websocket.receive_json()
            client_id = data.get("client_id")

            client_info = server.get_client(client_id)
            if not client_info:
                await websocket.close(code=4000)
                return

            client_info.status = ClientStatus.ONLINE
            server.heartbeat(client_id)

            while True:
                order = server.get_next_order()
                if order:
                    server.assign_order(order, client_id)
                    await websocket.send_json({
                        "type": "order",
                        "order": order.model_dump(mode="json"),
                    })
                else:
                    await asyncio.sleep(5)

                try:
                    msg = await asyncio.wait_for(
                        websocket.receive_json(), timeout=1
                    )
                    if msg.get("type") == "heartbeat":
                        server.heartbeat(client_id)
                except asyncio.TimeoutError:
                    pass

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.error("Order WebSocket error: %s", exc)
        finally:
            if client_id:
                server.unregister_client(client_id)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return get_dashboard_html()

    return app


def get_dashboard_html() -> str:
    """Return the dashboard HTML."""
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "    <meta charset=\"UTF-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"  # noqa: E501
        "    <title>spotDL Remote Dashboard</title>\n"
        "    <style>\n"
        "        * { box-sizing: border-box; margin: 0; padding: 0; }\n"
        "        body {\n"
        "            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',\n"
        "                Roboto, sans-serif;\n"
        "            background: #0f172a;\n"
        "            color: #e2e8f0;\n"
        "            padding: 20px;\n"
        "        }\n"
        "        h1 { color: #38bdf8; margin-bottom: 20px; }\n"
        "        .grid {\n"
        "            display: grid;\n"
        "            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));\n"
        "            gap: 20px;\n"
        "        }\n"
        "        .card {\n"
        "            background: #1e293b;\n"
        "            border-radius: 8px;\n"
        "            padding: 20px;\n"
        "        }\n"
        "        .card h2 {\n"
        "            color: #94a3b8;\n"
        "            font-size: 14px;\n"
        "            text-transform: uppercase;\n"
        "            letter-spacing: 1px;\n"
        "            margin-bottom: 10px;\n"
        "        }\n"
        "        .stat {\n"
        "            font-size: 32px;\n"
        "            font-weight: bold;\n"
        "            color: #38bdf8;\n"
        "        }\n"
        "        .btn {\n"
        "            background: #38bdf8;\n"
        "            color: #0f172a;\n"
        "            border: none;\n"
        "            padding: 10px 20px;\n"
        "            border-radius: 6px;\n"
        "            cursor: pointer;\n"
        "            font-weight: bold;\n"
        "        }\n"
        "        .btn:hover { background: #0ea5e9; }\n"
        "        table {\n"
        "            width: 100%;\n"
        "            border-collapse: collapse;\n"
        "            margin-top: 10px;\n"
        "        }\n"
        "        th, td {\n"
        "            text-align: left;\n"
        "            padding: 8px;\n"
        "            border-bottom: 1px solid #334155;\n"
        "        }\n"
        "        th { color: #94a3b8; font-weight: 500; }\n"
        "        .status-pending { color: #fbbf24; }\n"
        "        .status-completed { color: #34d399; }\n"
        "        .status-failed { color: #f87171; }\n"
        "        .status-downloading { color: #60a5fa; }\n"
        "    </style>\n"
        "</head>\n"
        "<body>\n"
        "    <h1>spotDL Remote Dashboard</h1>\n"
        "    <div class=\"grid\">\n"
        "        <div class=\"card\">\n"
        "            <h2>Queue Stats</h2>\n"
        "            <div id=\"queue-stats\">Loading...</div>\n"
        "        </div>\n"
        "        <div class=\"card\">\n"
        "            <h2>Connected Clients</h2>\n"
        "            <div id=\"client-count\">Loading...</div>\n"
        "        </div>\n"
        "    </div>\n"
        "    <div class=\"card\" style=\"margin-top: 20px;\">\n"
        "        <h2>Recent Orders</h2>\n"
        "        <table>\n"
        "            <thead><tr><th>ID</th><th>Query</th>"
        "<th>Status</th><th>Client</th></tr></thead>\n"
        "            <tbody id=\"orders-table\">"
        "<tr><td colspan=\"4\">Loading...</td></tr></tbody>\n"
        "        </table>\n"
        "    </div>\n"
        "    <script>\n"
        "        async function loadData() {\n"
        "            const statusRes = await fetch('/api/status');\n"
        "            const status = await statusRes.json();\n"
        "            document.getElementById('queue-stats').innerHTML =\n"
        "                Object.entries(status.queue).map(([k, v]) => {\n"
        "                    return `<div><strong>${k}:</strong> ${v}</div>`;\n"
        "                }).join('');\n"
        "            document.getElementById('client-count').textContent =\n"
        "                status.clients.active + ' / ' +\n"
        "                status.clients.total + ' active';\n"
        "\n"
        "            const ordersRes = await fetch('/api/orders?limit=20');\n"
        "            const orders = await ordersRes.json();\n"
        "            const tbody = document.getElementById('orders-table');\n"
        "            tbody.innerHTML = orders.map(o => `<tr>\n"
        "                <td>${o.order_id}</td>\n"
        "                <td>${o.query.substring(0, 50)}</td>\n"
        "                <td class=\"status-${o.status}\">${o.status}</td>\n"
        "                <td>${o.client_id || '-'}</td>\n"
        "            </tr>`).join('');\n"
        "        }\n"
        "        setInterval(loadData, 5000);\n"
        "        loadData();\n"
        "    </script>\n"
        "</body>\n"
        "</html>"
    )
