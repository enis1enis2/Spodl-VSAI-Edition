"""
Remote client/server console module.
"""

import argparse
import asyncio
import logging
import sys

from spotdl.remote.client import RemoteClient
from spotdl.remote.models import ClientInfo
from spotdl.remote.server import RemoteServer, create_app
from spotdl.types.options import DownloaderOptions
from spotdl.utils.config import create_settings
from spotdl.utils.ffmpeg import is_ffmpeg_installed

__all__ = ["remote"]


logger = logging.getLogger(__name__)


def _run_server(host: str, port: int, downloader_settings: DownloaderOptions):
    """Run the remote server."""
    import uvicorn

    server = RemoteServer(
        downloader_settings=downloader_settings,
        host=host,
        port=port,
    )
    app = create_app(server)

    print(f"Starting spotDL Remote Server on http://{host}:{port}")
    print(f"Dashboard: http://{host}:{port}/dashboard")
    print(f"API docs: http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port, log_level="info")


def _run_client(server_url: str, download_dir: str, downloader_settings: DownloaderOptions):
    """Run the remote client."""
    if not is_ffmpeg_installed(downloader_settings.get("ffmpeg", "ffmpeg")):
        print("Error: ffmpeg is not installed. Please install ffmpeg first.")
        sys.exit(1)

    client = RemoteClient(
        server_url=server_url,
        downloader_settings=downloader_settings,
        download_dir=download_dir,
    )

    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:
        print("\nClient stopped.")
        client.stop()


def remote(args: argparse.Namespace):
    """
    Run the remote client or server.

    ### Arguments
    - args: The parsed arguments.
    """
    spotify_settings, downloader_settings, web_settings = create_settings(args)

    if args.remote_mode == "server":
        host = args.remote_host or web_settings.get("host", "0.0.0.0")
        port = args.remote_port or web_settings.get("port", 8801)
        _run_server(host, port, downloader_settings)

    elif args.remote_mode == "client":
        server_url = args.remote_server or "http://localhost:8801"
        download_dir = args.remote_download_dir or downloader_settings.get("output", "./downloads")
        _run_client(server_url, download_dir, downloader_settings)

    else:
        print("Usage: spotdl remote <server|client> [options]")
        print("\nServer options:")
        print("  --remote-host HOST       Host to bind to (default: 0.0.0.0)")
        print("  --remote-port PORT       Port to listen on (default: 8801)")
        print("\nClient options:")
        print("  --remote-server URL      Server URL (default: http://localhost:8801)")
        print("  --remote-download-dir DIR Download directory (default: from settings)")
        sys.exit(1)


def add_remote_subparser(subparsers):
    """Add remote subparser to the argument parser."""
    remote_parser = subparsers.add_parser(
        "remote",
        help="Run remote client or server for distributed downloads",
        description=(
            "Run a spotDL remote server to manage download clients, "
            "or run a client to receive and process download orders."
        ),
    )

    remote_parser.add_argument(
        "remote_mode",
        choices=["server", "client"],
        help="Whether to run as server or client",
    )

    remote_parser.add_argument(
        "--remote-host",
        help="Host to bind the server to (server mode only)",
    )

    remote_parser.add_argument(
        "--remote-port",
        type=int,
        help="Port to listen on (server mode only)",
    )

    remote_parser.add_argument(
        "--remote-server",
        help="Server URL to connect to (client mode only)",
    )

    remote_parser.add_argument(
        "--remote-download-dir",
        help="Directory to save downloaded files (client mode only)",
    )

    remote_parser.set_defaults(func=remote)
