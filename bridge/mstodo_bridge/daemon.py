"""ESP32 Bridge Daemon — HTTP and/or MQTT modes.

Usage:
  python -m bridge.mstodo_bridge.daemon http [--host 0.0.0.0] [--port 7070]
  python -m bridge.mstodo_bridge.daemon mqtt [--broker <IP>] [--port 1883] ...
  python -m bridge.mstodo_bridge.daemon both [--http-host ...] [--mqtt-broker ...]
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from http.server import HTTPServer

from .http_api import BridgeHTTPHandler

logging.basicConfig(
    level=logging.INFO,
    format="[bridge] %(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def run_http(host: str, port: int) -> HTTPServer:
    server = HTTPServer((host, port), BridgeHTTPHandler)
    logger.info("HTTP server listening on %s:%d", host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_mqtt(args: argparse.Namespace):
    from .mqtt.publish import MQTTBridge

    bridge = MQTTBridge(
        broker=args.mqtt_broker,
        port=args.mqtt_port,
        username=args.mqtt_username,
        password=args.mqtt_password,
        device_id=args.device_id,
        topic_prefix=args.topic_prefix,
        publish_interval=args.publish_interval,
        task_limit=args.limit,
    )
    bridge.start()
    return bridge


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mstodo-bridge",
        description="ESP32 Bridge Daemon — syncs Microsoft To Do with ESP32 devices",
    )
    sub = ap.add_subparsers(dest="mode", required=True)

    # HTTP mode
    p_http = sub.add_parser("http", help="HTTP server mode")
    p_http.add_argument("--host", default="0.0.0.0")
    p_http.add_argument("--port", type=int, default=7070)

    # MQTT mode
    p_mqtt = sub.add_parser("mqtt", help="MQTT pub/sub mode")
    p_mqtt.add_argument("--mqtt-broker", required=True, help="MQTT broker host")
    p_mqtt.add_argument("--mqtt-port", type=int, default=1883)
    p_mqtt.add_argument("--mqtt-username", default=None)
    p_mqtt.add_argument("--mqtt-password", default=None)
    p_mqtt.add_argument("--device-id", default="esp32-1")
    p_mqtt.add_argument("--topic-prefix", default="mstodo")
    p_mqtt.add_argument("--publish-interval", type=int, default=60)
    p_mqtt.add_argument("--limit", type=int, default=6)

    # Both mode
    p_both = sub.add_parser("both", help="HTTP + MQTT combined")
    p_both.add_argument("--host", default="0.0.0.0")
    p_both.add_argument("--port", type=int, default=7070)
    p_both.add_argument("--mqtt-broker", required=True)
    p_both.add_argument("--mqtt-port", type=int, default=1883)
    p_both.add_argument("--mqtt-username", default=None)
    p_both.add_argument("--mqtt-password", default=None)
    p_both.add_argument("--device-id", default="esp32-1")
    p_both.add_argument("--topic-prefix", default="mstodo")
    p_both.add_argument("--publish-interval", type=int, default=60)
    p_both.add_argument("--limit", type=int, default=6)

    return ap


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    stop_event = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Shutting down (signal %d)...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    http_server = None
    mqtt_bridge = None

    if args.mode in ("http", "both"):
        http_server = run_http(args.host, args.port)

    if args.mode in ("mqtt", "both"):
        mqtt_bridge = run_mqtt(args)

    logger.info("Bridge running in %s mode. Press Ctrl+C to stop.", args.mode)

    try:
        stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if http_server:
            http_server.shutdown()
            logger.info("HTTP server stopped")
        if mqtt_bridge:
            mqtt_bridge.stop()

    logger.info("Bridge daemon exited.")


if __name__ == "__main__":
    main()
