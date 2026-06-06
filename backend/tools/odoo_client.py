"""
Odoo XML-RPC client wrapper.
Tất cả agent đều dùng client này để CRUD Odoo.
"""
from __future__ import annotations

import os
import xmlrpc.client
from functools import lru_cache
from typing import Any


class OdooClient:
    def __init__(self, url: str, db: str, username: str, password: str) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self._uid: int | None = None
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    # ---- auth ----
    @property
    def uid(self) -> int:
        if self._uid is None:
            self._uid = self._common.authenticate(self.db, self.username, self.password, {})
            if not self._uid:
                raise RuntimeError("Odoo authentication failed - kiểm tra ODOO_USERNAME/ODOO_PASSWORD")
        return self._uid

    # ---- generic CRUD ----
    def execute(self, model: str, method: str, args: list, kwargs: dict | None = None) -> Any:
        return self._models.execute_kw(self.db, self.uid, self.password, model, method, args, kwargs or {})

    def search_read(
        self, model: str, domain: list | None = None, fields: list[str] | None = None,
        limit: int = 80, offset: int = 0, order: str | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"fields": fields or [], "limit": limit, "offset": offset}
        if order:
            kwargs["order"] = order
        return self.execute(model, "search_read", [domain or []], kwargs)

    def read(self, model: str, ids: list[int], fields: list[str] | None = None) -> list[dict]:
        return self.execute(model, "read", [ids], {"fields": fields or []})

    def create(self, model: str, values: dict) -> int:
        return self.execute(model, "create", [values])

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        return self.execute(model, "write", [ids, values])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute(model, "unlink", [ids])

    def search_count(self, model: str, domain: list | None = None) -> int:
        return self.execute(model, "search_count", [domain or []])


@lru_cache(maxsize=1)
def get_odoo() -> OdooClient:
    return OdooClient(
        url=os.getenv("ODOO_URL", "http://localhost:8069"),
        db=os.getenv("ODOO_DB", "odoo"),
        username=os.getenv("ODOO_USERNAME", "admin"),
        password=os.getenv("ODOO_PASSWORD", "admin"),
    )
