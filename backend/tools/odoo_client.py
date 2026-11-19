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

    def aggregate(
        self, model: str, domain: list | None, groupby: list[str], aggregates: list[str],
        order: str | None = None, limit: int | None = None,
    ) -> list[dict]:
        """Tổng hợp phía server (Postgres GROUP BY) thay vì kéo record về rồi cộng.

        aggregates dạng "field:agg" (vd "amount_total:sum") hoặc "__count".
        Mỗi dòng trả về có key là groupby và đúng chuỗi aggregate; many2one là [id, tên].
        groupby rỗng → 1 dòng tổng.

        Odoo 19+: formatted_read_group (read_group đã deprecated từ 19.0).
        Odoo cũ hơn: read_group(lazy=False), đổi key về cùng định dạng.
        """
        kwargs: dict[str, Any] = {"groupby": groupby, "aggregates": aggregates}
        if order:
            kwargs["order"] = order
        if limit:
            kwargs["limit"] = limit
        try:
            return self.execute(model, "formatted_read_group", [domain or []], kwargs)
        except xmlrpc.client.Fault as exc:
            if "formatted_read_group" not in str(exc) or "does not exist" not in str(exc):
                raise

        fields = [a for a in aggregates if a != "__count"]
        legacy: dict[str, Any] = {"groupby": groupby, "lazy": False}
        if order:
            legacy["orderby"] = order.replace(":sum", "").replace(":count", "")
        if limit:
            legacy["limit"] = limit
        rows = self.execute(model, "read_group", [domain or [], fields, groupby], legacy)
        out = []
        for row in rows:
            item = {g: row.get(g) for g in groupby}
            for spec in fields:
                item[spec] = row.get(spec.split(":", 1)[0])
            if "__count" in aggregates:
                item["__count"] = row.get("__count", 0)
            out.append(item)
        return out


@lru_cache(maxsize=1)
def get_odoo() -> OdooClient:
    return OdooClient(
        url=os.getenv("ODOO_URL", "http://localhost:8069"),
        db=os.getenv("ODOO_DB", "odoo"),
        username=os.getenv("ODOO_USERNAME", "admin"),
        password=os.getenv("ODOO_PASSWORD", "admin"),
    )
