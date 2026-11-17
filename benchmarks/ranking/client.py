"""The REST calls the ranking benchmark makes, and nothing else.

Standard library only, so the benchmark runs against any KATO instance from any
Python without installing KATO's dependencies.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class KatoError(RuntimeError):
    """KATO answered with an HTTP error."""

    def __init__(self, status: int, detail: str, call: str):
        super().__init__(f"{call} -> HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class Kato:
    """A KATO instance, reached over HTTP.

    `transport(method, path, payload)` returns the decoded JSON body and raises
    KatoError for an HTTP error. The default speaks HTTP to `base_url`; tests
    pass their own.
    """

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 900.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport or self._http

    def _http(self, method: str, path: str, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:2000]
            raise KatoError(error.code, detail, f"{method} {path}") from None

    def call(self, method: str, path: str, payload=None):
        return self._transport(method, path, payload)

    # ------------------------------------------------------------------ the service

    def info(self) -> dict:
        return self.call("GET", "/")

    def healthy(self) -> bool:
        try:
            self.call("GET", "/health")
        except (KatoError, OSError):
            return False
        return True

    def pattern_count(self, node_id: str) -> int:
        query = urllib.parse.urlencode({"node_id": node_id, "flush": "true"})
        return int(self.call("GET", f"/patterns/count?{query}")["pattern_count"])

    # ------------------------------------------------------------------ sessions

    def new_session(self, node_id: str, config: dict) -> str:
        return self.call("POST", "/sessions", {"node_id": node_id, "config": config})["session_id"]

    def delete_session(self, session: str) -> None:
        self.call("DELETE", f"/sessions/{session}")

    def configure(self, session: str, config: dict) -> None:
        self.call("POST", f"/sessions/{session}/config", {"config": config})

    def clear_stm(self, session: str) -> None:
        self.call("POST", f"/sessions/{session}/clear-stm", {})

    def clear_node(self, session: str) -> None:
        """Remove every pattern of the session's node."""
        self.call("POST", f"/sessions/{session}/clear-all", {})

    def finalize_training(self, session: str) -> dict:
        return self.call("POST", f"/sessions/{session}/finalize-training", {})

    def observe(self, session: str, events: list, learn: bool = False) -> dict:
        """Observe events in order. With `learn`, the STM is learned as one pattern afterwards."""
        return self.call("POST", f"/sessions/{session}/observe-sequence", {
            "observations": [{"strings": list(event)} for event in events],
            "learn_at_end": learn,
        })

    def predictions(self, session: str) -> dict:
        return self.call("GET", f"/sessions/{session}/predictions")
