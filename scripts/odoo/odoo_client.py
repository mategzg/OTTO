"""Odoo XML-RPC client with secure/auditable defaults.

Internal toolkit module for OTTO.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Sequence
from xmlrpc.client import Fault, ProtocolError, ServerProxy, Transport


LOGGER = logging.getLogger("otto.odoo.client")


def _mask_secret(value: Optional[str], keep: int = 2) -> str:
    if not value:
        return "***"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}***{value[-keep:]}"


class TimeoutTransport(Transport):
    """XML-RPC transport with configurable socket timeout."""

    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):  # type: ignore[override]
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


@dataclass(frozen=True)
class OdooConfig:
    url: str
    db: str
    username: str
    password: str
    timeout_seconds: float = 15.0
    retries: int = 3
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls, prefix: str = "ODOO_") -> "OdooConfig":
        return cls(
            url=os.environ[f"{prefix}URL"],
            db=os.environ[f"{prefix}DB"],
            username=os.environ[f"{prefix}USERNAME"],
            password=os.environ[f"{prefix}PASSWORD"],
            timeout_seconds=float(os.getenv(f"{prefix}TIMEOUT", "15")),
            retries=int(os.getenv(f"{prefix}RETRIES", "3")),
            retry_backoff_seconds=float(os.getenv(f"{prefix}RETRY_BACKOFF", "0.5")),
        )


class OdooClientError(RuntimeError):
    pass


class OdooAuthError(OdooClientError):
    pass


class OdooExecutionError(OdooClientError):
    pass


class OdooClient:
    def __init__(self, config: OdooConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or LOGGER
        self._uid: Optional[int] = None
        transport = TimeoutTransport(timeout=config.timeout_seconds)
        self._common = ServerProxy(
            f"{config.url.rstrip('/')}/xmlrpc/2/common", allow_none=True, transport=transport
        )
        self._models = ServerProxy(
            f"{config.url.rstrip('/')}/xmlrpc/2/object", allow_none=True, transport=transport
        )

    @property
    def uid(self) -> int:
        if self._uid is None:
            raise OdooAuthError("Client not authenticated. Call authenticate() first.")
        return self._uid

    def _audit(self, event: str, **payload: Any) -> None:
        safe_payload = dict(payload)
        if "password" in safe_payload:
            safe_payload["password"] = _mask_secret(str(safe_payload["password"]))
        safe_payload["ts"] = datetime.now(timezone.utc).isoformat()
        self.logger.info("odoo_audit %s", json.dumps({"event": event, **safe_payload}, default=str))

    def _with_retries(self, fn, op_name: str):
        last_exc: Optional[Exception] = None
        attempts = max(1, self.config.retries)
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except (Fault, ProtocolError, socket.timeout, OSError) as exc:
                last_exc = exc
                retriable = attempt < attempts
                self._audit(
                    "retry",
                    operation=op_name,
                    attempt=attempt,
                    retries=attempts,
                    error=str(exc),
                    retriable=retriable,
                )
                if not retriable:
                    break
                sleep_for = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                time.sleep(sleep_for)
        raise OdooExecutionError(f"{op_name} failed after {attempts} attempts: {last_exc}")

    def authenticate(self, force: bool = False) -> int:
        if self._uid is not None and not force:
            return self._uid

        self._audit(
            "auth_start",
            url=self.config.url,
            db=self.config.db,
            username=self.config.username,
            password=self.config.password,
        )

        def _call_auth():
            return self._common.authenticate(
                self.config.db,
                self.config.username,
                self.config.password,
                {},
            )

        uid = self._with_retries(_call_auth, "authenticate")
        if not uid:
            self._audit("auth_failed", username=self.config.username, db=self.config.db)
            raise OdooAuthError("Odoo authentication failed: invalid credentials or permissions.")

        self._uid = int(uid)
        self._audit("auth_ok", uid=self._uid, username=self.config.username, db=self.config.db)
        return self._uid

    def execute_kw(
        self,
        model: str,
        method: str,
        args: Optional[Sequence[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        *,
        ensure_auth: bool = True,
    ) -> Any:
        if ensure_auth:
            self.authenticate()

        args = list(args or [])
        kwargs = dict(kwargs or {})

        self._audit(
            "execute_start",
            model=model,
            method=method,
            args_preview=str(args)[:300],
            kwargs_preview=str(kwargs)[:300],
        )

        def _call_execute():
            return self._models.execute_kw(
                self.config.db,
                self.uid,
                self.config.password,
                model,
                method,
                args,
                kwargs,
            )

        result = self._with_retries(_call_execute, f"execute_kw:{model}.{method}")
        self._audit(
            "execute_ok",
            model=model,
            method=method,
            result_type=type(result).__name__,
        )
        return result


def configure_default_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
