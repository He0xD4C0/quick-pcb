"""HTTP client for the official EasyEDA WebSocket bridge.

The bridge is provided by ``easyeda-api-skill`` (``run-api-gateway.eext`` +
Node server). It listens on an available port in the 49620–49629 range and
exposes:

- ``GET /health``     -> ``200`` when the EDA client is connected.
- ``POST /execute``   -> ``{"code": "<JS>", "windowId": "..."}`` targets one window.

This client never falls back to fabricating part/pin data: when the bridge is
unreachable, callers must surface ``BRIDGE_UNAVAILABLE`` rather than guess.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

DEFAULT_PORT_RANGE = range(49620, 49630)
DEFAULT_TIMEOUT = 15.0
SERVICE_ID = "easyeda-bridge"


class BridgeError(Exception):
    """Raised when the bridge is unreachable or returns an error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BridgeClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        port_range=DEFAULT_PORT_RANGE,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = (base_url or os.environ.get("BOARDSPEC_BRIDGE_URL") or "").rstrip("/")
        self._configured = bool(self.base_url)
        self.port_range = port_range
        self.timeout = timeout
        self._resolved: Optional[str] = self.base_url or None

    def _candidates(self):
        if self._configured:
            return [self.base_url]
        return [f"http://127.0.0.1:{port}" for port in self.port_range]

    def _probe(self, url: str) -> bool:
        try:
            r = httpx.get(f"{url}/health", timeout=min(self.timeout, 2.0))
            if not r.is_success:
                return False
            data = r.json()
            return data.get("service") == SERVICE_ID
        except (httpx.HTTPError, ValueError):
            return False

    def resolve_base_url(self) -> str:
        """Find a reachable bridge, raising BridgeError if none responds."""
        if self._resolved and self._probe(self._resolved):
            return self._resolved
        for url in self._candidates():
            if self._probe(url):
                self._resolved = url
                return url
        raise BridgeError(
            "BRIDGE_UNAVAILABLE",
            "no EasyEDA bridge reachable on ports 49620-49629; "
            "start the bridge and load run-api-gateway.eext in EasyEDA Pro",
        )

    def health(self) -> dict:
        try:
            url = self.resolve_base_url()
        except BridgeError as e:
            return {"ok": False, "code": e.code, "message": e.message}
        try:
            r = httpx.get(f"{url}/health", timeout=min(self.timeout, 2.0))
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            return {"ok": False, "code": "BRIDGE_HTTP_ERROR", "message": str(exc)}
        except ValueError:
            return {
                "ok": False,
                "code": "BRIDGE_BAD_RESPONSE",
                "message": "bridge health endpoint returned non-JSON data",
            }
        if data.get("service") != SERVICE_ID:
            return {
                "ok": False,
                "code": "BRIDGE_BAD_RESPONSE",
                "message": "health endpoint is not an EasyEDA bridge",
            }
        if not data.get("edaConnected"):
            return {
                "ok": False,
                "code": "EDA_UNAVAILABLE",
                "message": "EasyEDA bridge is running, but no EDA window is connected",
                "base_url": url,
            }
        return {
            "ok": True,
            "base_url": url,
            "eda_window_count": data.get("edaWindowCount", 0),
            "active_window_id": data.get("activeWindowId"),
        }

    def list_windows(self) -> dict:
        """Return connected EDA windows without changing the active window."""
        try:
            url = self.resolve_base_url()
            r = httpx.get(f"{url}/eda-windows", timeout=min(self.timeout, 5.0))
            r.raise_for_status()
            data = r.json()
        except BridgeError as exc:
            return {"ok": False, "code": exc.code, "message": exc.message}
        except httpx.TimeoutException as exc:
            return {"ok": False, "code": "BRIDGE_TIMEOUT", "message": str(exc)}
        except httpx.HTTPError as exc:
            return {"ok": False, "code": "BRIDGE_HTTP_ERROR", "message": str(exc)}
        except ValueError:
            return {
                "ok": False,
                "code": "BRIDGE_BAD_RESPONSE",
                "message": "bridge window endpoint returned non-JSON data",
            }
        raw_windows = data.get("windows") if isinstance(data, dict) else None
        if not isinstance(raw_windows, list):
            return {
                "ok": False,
                "code": "BRIDGE_BAD_RESPONSE",
                "message": "bridge window endpoint returned no window list",
            }
        windows = [
            {**item, "id": item.get("id") or item.get("windowId")}
            for item in raw_windows
            if isinstance(item, dict)
        ]
        return {
            "ok": True,
            "base_url": url,
            "active_window_id": data.get("activeWindowId"),
            "windows": windows,
        }

    def execute(self, code: str, window_id: str | None = None) -> dict:
        """Run JS inside EasyEDA Pro and return ``{ok, result|error}``."""
        try:
            url = self.resolve_base_url()
        except BridgeError as e:
            return {"ok": False, "code": e.code, "message": e.message}

        try:
            r = httpx.post(
                f"{url}/execute",
                json={
                    "code": code,
                    **({"windowId": window_id} if window_id else {}),
                },
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            return {"ok": False, "code": "BRIDGE_TIMEOUT", "message": str(exc)}
        except httpx.HTTPError as exc:
            return {"ok": False, "code": "BRIDGE_HTTP_ERROR", "message": str(exc)}

        if not r.is_success:
            return {
                "ok": False,
                "code": "BRIDGE_HTTP_ERROR",
                "message": f"bridge returned HTTP {r.status_code}",
                "status_code": r.status_code,
            }

        try:
            data = r.json()
        except ValueError:
            return {
                "ok": False,
                "code": "BRIDGE_BAD_RESPONSE",
                "message": f"non-JSON response (HTTP {r.status_code})",
            }

        # The bridge returns {type: 'result'|'error', ...}; normalize to ok.
        if data.get("type") == "error" or data.get("error") is not None:
            return {
                "ok": False,
                "code": "EDA_EXECUTION_ERROR",
                "message": str(data.get("error") or data),
            }
        return {"ok": True, "result": data.get("result", data)}
