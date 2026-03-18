"""MQTT publish/subscribe handler for ESP32 bridge.

Topics:
  {prefix}/{device_id}/tasks   — publish task snapshots (JSON)
  {prefix}/{device_id}/cmd     — subscribe for commands from ESP32
  {prefix}/{device_id}/ack     — publish command acknowledgements
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # type: ignore[assignment]


class MQTTBridge:
    """MQTT bridge for ESP32 task synchronization."""

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        device_id: str = "esp32-1",
        topic_prefix: str = "mstodo",
        publish_interval: int = 60,
        task_limit: int = 6,
    ):
        if mqtt is None:
            raise ImportError(
                "paho-mqtt is required for MQTT mode. Install: pip install paho-mqtt"
            )

        self.broker = broker
        self.port = port
        self.device_id = device_id
        self.topic_prefix = topic_prefix
        self.publish_interval = publish_interval
        self.task_limit = task_limit
        self._stop = threading.Event()

        self.client = mqtt.Client(client_id=f"mstodo-bridge-{device_id}")
        if username:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    @property
    def _topic_tasks(self) -> str:
        return f"{self.topic_prefix}/{self.device_id}/tasks"

    @property
    def _topic_cmd(self) -> str:
        return f"{self.topic_prefix}/{self.device_id}/cmd"

    @property
    def _topic_ack(self) -> str:
        return f"{self.topic_prefix}/{self.device_id}/ack"

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            logger.info("MQTT connected to %s:%d", self.broker, self.port)
            client.subscribe(self._topic_cmd)
            logger.info("Subscribed to %s", self._topic_cmd)
        else:
            logger.error("MQTT connection failed: rc=%d", rc)

    def _on_message(self, client, userdata, msg) -> None:
        """Handle incoming command from ESP32."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.info("CMD received: %s", payload)

            op = payload.get("op", "")
            task_id = payload.get("task_id", "")
            list_id = payload.get("list_id")
            completed = payload.get("completed")

            kwargs = {}
            if op == "set_completed":
                if not isinstance(completed, bool):
                    raise RuntimeError(
                        "missing or invalid 'completed' for set_completed"
                    )
                if completed:
                    op = "complete"
                else:
                    op = "update"
                    kwargs["status"] = "notStarted"

            from ..snapshot import execute_command

            result = execute_command(op=op, task_id=task_id, list_id=list_id, **kwargs)
            ack = {"success": True, "op": op, "task_id": task_id, "data": result}

        except Exception as e:
            logger.exception("Command execution failed: %s", e)
            ack = {"success": False, "error": str(e)}

        self.client.publish(self._topic_ack, json.dumps(ack, ensure_ascii=False))

    def _publish_loop(self) -> None:
        """Periodically publish task snapshots."""
        from ..snapshot import build_snapshot

        while not self._stop.is_set():
            try:
                snapshot = build_snapshot(
                    device_id=self.device_id,
                    limit=self.task_limit,
                )
                payload = json.dumps(snapshot.to_dict(), ensure_ascii=False)
                self.client.publish(self._topic_tasks, payload, retain=True)
                logger.debug("Published snapshot to %s", self._topic_tasks)
            except Exception as e:
                logger.error("Failed to publish snapshot: %s", e)

            self._stop.wait(self.publish_interval)

    def start(self) -> None:
        """Connect and start the MQTT bridge."""
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

        self._publish_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self._publish_thread.start()

    def stop(self) -> None:
        """Stop the MQTT bridge."""
        self._stop.set()
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("MQTT bridge stopped")
