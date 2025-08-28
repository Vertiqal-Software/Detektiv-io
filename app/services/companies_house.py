# app/services/companies_house.py
from __future__ import annotations

import os
import secrets
import time
import random
import logging
from typing import Any, Dict, List, Optional, Tuple, Iterable
from threading import Lock

import requests
from requests import Response
from requests.exceptions import RequestException


class CompaniesHouseError(RuntimeError):
    pass


# ---------------------------
# Environment helpers
# ---------------------------
def _env_api_key() -> Optional[str]:
    # Single place to read; can be overridden in tests
    return os.getenv("CH_API_KEY") or os.getenv("COMPANIES_HOUSE_API_KEY")


def _env_timeout(default: float) -> float:
    raw = os.getenv("CH_TIMEOUT")
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:  # nosec B110
        return default


def _env_user_agent(default: str) -> str:
    return os.getenv("CH_USER_AGENT", default)


def _env_min_interval(default: float = 0.0) -> float:
    raw = os.getenv("CH_MIN_REQUEST_INTERVAL", "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
        return max(0.0, v)
    except Exception:  # nosec B110
        return default


def _cap_page(value: int, lo: int = 1, hi: int = 100) -> int:
    try:
        v = int(value)
    except Exception:  # nosec B110
        v = hi
    return max(lo, min(hi, v))


# ---------------------------
# Simple per-key throttle (process-local)
# ---------------------------
_rate_lock = Lock()
_last_call_by_key: Dict[str, float] = {}


def _throttle_for_key(api_key: str, min_interval: float) -> None:
    """
    Ensure a minimum interval between calls per API key (process-local).
    If we haven't waited long enough since the last call, sleep the remainder.
    """
    if min_interval <= 0:
        return
    now = time.monotonic()
    with _rate_lock:
        last = _last_call_by_key.get(api_key)
        if last is None:
            _last_call_by_key[api_key] = now
            return
        elapsed = now - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_call_by_key[api_key] = time.monotonic()  # update after any sleep


class CompaniesHouseClient:
    """
    Thin wrapper over the Companies House REST API.

    Coverage:
      - Basic search (GET /search/companies)
      - Advanced search (GET /advanced-search/companies)
      - Company profile
      - Officers (paginated)
      - Filing history (paginated)
      - PSCs (individual / corporate / legal person / statements) (paginated)
      - Charges (paginated)
      - Insolvency
      - Exemptions
      - Registers
      - UK establishments (paginated)
      - Officer appointments (by officer_id) (paginated)
    """

    DEFAULT_BASE_URL = "https://api.company-information.service.gov.uk"
    UA = "detecktiv-io/1.0 (+https://detecktiv.io)"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 20.0,
        retry: int = 2,
        backoff: float = 0.6,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key or _env_api_key()
        if not self.api_key:
            raise CompaniesHouseError("Missing CH_API_KEY in environment")

        # Config
        self.timeout = _env_timeout(timeout)
        self.retry = max(0, int(retry))
        self.backoff = max(0.0, float(backoff))
        # Allow overriding base URL via env for sandbox/testing
        self.BASE_URL = base_url or os.getenv("CH_BASE_URL") or self.DEFAULT_BASE_URL
        self.USER_AGENT = _env_user_agent(self.UA)
        self.min_interval = _env_min_interval(0.0)  # seconds; 0 disables

        # HTTP session
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": self.USER_AGENT})
        # HTTP Basic (username=API_KEY, password="")
        self._session.auth = (self.api_key, "")

        self._log = logging.getLogger("ch.client")

    # ---------- lifecycle ----------
    def close(self) -> None:
        try:
            self._session.close()
        except Exception:  # nosec B110
            pass

    def __enter__(self) -> "CompaniesHouseClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---------- internal helpers ----------
    def _sleep_with_jitter(self, base: float, attempt: int) -> None:
        """
        Small full jitter to avoid synchronized retries in multi-tenant scenarios.
        """
        delay = max(0.0, base) * (2**attempt if attempt > 0 else 1.0)
        jitter = (
            (secrets.randbelow(1000000) / 1000000.0) * (delay * 0.25)
            if delay > 0
            else 0.0
        )  # nosec B311 - non-crypto backoff jitter
        time.sleep(delay + jitter)

    def _should_retry_status(self, status: int) -> bool:
        """
        Retry only server-side/transient conditions.
        """
        if status == 429:
            return True
        if 500 <= status <= 599:
            return True
        return False

    def _err_message(self, path: str, resp: Response) -> str:
        # Make a concise message; avoid dumping whole bodies
        snippet = ""
        try:
            j = resp.json()
            # prefer "error" / "errors" fields if present
            if isinstance(j, dict):
                if "error" in j and isinstance(j["error"], str):
                    snippet = j["error"]
                elif "errors" in j:
                    snippet = str(j["errors"])[:300]
                else:
                    snippet = str(j)[:300]
            else:
                snippet = str(j)[:300]
        except Exception:  # nosec B110
            try:
                snippet = (resp.text or "")[:300]
            except Exception:  # nosec B110
                snippet = ""
        return f"{resp.status_code} {resp.reason} on {path}" + (
            f": {snippet}" if snippet else ""
        )

    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(self.retry + 1):
            # Process-local throttle per API key
            _throttle_for_key(self.api_key, self.min_interval)

            try:
                resp = self._session.get(url, params=params or {}, timeout=self.timeout)

                # 401 -> immediate failure (never retry)
                if resp.status_code == 401:
                    raise CompaniesHouseError(
                        "Companies House API returned 401 Unauthorized "
                        "(check CH_API_KEY / COMPANIES_HOUSE_API_KEY)"
                    )

                # 429 -> honor Retry-After header if present, otherwise back off
                if resp.status_code == 429:
                    ra = resp.headers.get("Retry-After")
                    if ra:
                        try:
                            sleep_for = float(ra)
                        except Exception:  # nosec B110
                            sleep_for = self.backoff * (attempt + 1)
                    else:
                        sleep_for = self.backoff * (attempt + 1)

                    self._log.warning(
                        "rate-limited",
                        extra={
                            "status": 429,
                            "path": path,
                            "attempt": attempt,
                            "sleep": sleep_for,
                        },
                    )
                    self._sleep_with_jitter(sleep_for, attempt)
                    continue

                # For 4xx (except 429 handled above) -> no retry
                if 400 <= resp.status_code < 500:
                    msg = self._err_message(path, resp)
                    raise CompaniesHouseError(msg)

                # For other errors, raise_for_status then handle as retryable if 5xx
                try:
                    resp.raise_for_status()
                except requests.HTTPError as he:
                    status = resp.status_code
                    msg = self._err_message(path, resp)
                    if self._should_retry_status(status) and attempt < self.retry:
                        self._log.warning(
                            "server-error",
                            extra={"status": status, "path": path, "attempt": attempt},
                        )
                        self._sleep_with_jitter(self.backoff, attempt)
                        last_exc = CompaniesHouseError(msg)
                        continue
                    raise CompaniesHouseError(msg) from he

                # be defensive about JSON decoding
                try:
                    data = resp.json()
                except Exception as je:  # nosec B110
                    raise CompaniesHouseError(f"Invalid JSON from {path}: {je}") from je

                # Success
                return data  # type: ignore[return-value]

            except CompaniesHouseError:
                # already a friendly message (401/4xx/JSON), don't wrap again
                raise
            except RequestException as e:
                # network-level issue; retry with backoff
                last_exc = e
                self._log.warning(
                    "network-error",
                    extra={"path": path, "attempt": attempt, "type": type(e).__name__},
                )
                if attempt < self.retry:
                    self._sleep_with_jitter(self.backoff, attempt)
                    continue
                break
            except Exception as e:  # pragma: no cover (unexpected)
                last_exc = e
                self._log.warning(
                    "unexpected-error",
                    extra={"path": path, "attempt": attempt, "type": type(e).__name__},
                )
                if attempt < self.retry:
                    self._sleep_with_jitter(self.backoff, attempt)
                    continue
                break

        raise CompaniesHouseError(f"GET {path} failed: {last_exc}")

    def _get_all_pages(
        self,
        path: str,
        item_key: str = "items",
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generic pager:
          - Fetch pages until we've read `total_results` or hit `max_items`.
          - Return {items: [...], total_results: int, raw_pages: [...]}
        """
        out_items: List[Dict[str, Any]] = []
        raw_pages: List[Dict[str, Any]] = []
        total_results: Optional[int] = None

        params = dict(extra_params or {})
        params["items_per_page"] = _cap_page(items_per_page)
        si = max(0, int(start_index))

        while True:
            params["start_index"] = si
            page = self._get(path, params=params)
            raw_pages.append(page)

            page_items = page.get(item_key) or page.get("items") or []
            if isinstance(page_items, list):
                out_items.extend(page_items)

            if total_results is None:
                total_results = page.get("total_results")

            if max_items is not None and len(out_items) >= max_items:
                out_items = out_items[:max_items]
                break

            if total_results is not None and len(out_items) >= total_results:
                break

            count_this_page = len(page_items) if isinstance(page_items, list) else 0
            if count_this_page < params["items_per_page"]:
                break

            si += count_this_page

        return {
            "items": out_items,
            "total_results": (
                total_results if total_results is not None else len(out_items)
            ),
            "raw_pages": raw_pages,
        }

    # ---------- exposed endpoints ----------

    # Basic search
    def search_companies(
        self,
        query: str,
        items_per_page: int = 20,
        start_index: int = 0,
        extra_params: Optional[Dict[str, Any]] = None,  # additive: pass-through filters
    ) -> Dict[str, Any]:
        params = dict(extra_params or {})
        params.update(
            {
                "q": query,
                "items_per_page": _cap_page(items_per_page),
                "start_index": max(0, int(start_index)),
            }
        )
        return self._get("/search/companies", params=params)

    # Advanced search (additive)
    def search_companies_advanced(
        self,
        query: str,
        items_per_page: int = 20,
        start_index: int = 0,
        extra_params: Optional[
            Dict[str, Any]
        ] = None,  # additive: pass-through advanced filters
    ) -> Dict[str, Any]:
        params = dict(extra_params or {})
        params.update(
            {
                "q": query,
                "items_per_page": _cap_page(items_per_page),
                "start_index": max(0, int(start_index)),
            }
        )
        return self._get("/advanced-search/companies", params=params)

    def get_company_profile(self, company_number: str) -> Dict[str, Any]:
        return self._get(f"/company/{company_number}")

    def get_company_officers(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/officers",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_company_filing_history(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/filing-history",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_company_psc_individuals(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/persons-with-significant-control/individual",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_company_psc_corporate(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/persons-with-significant-control/corporate-entity",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_company_psc_legal_person(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/persons-with-significant-control/legal-person",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_company_psc_statements(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/persons-with-significant-control-statements",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_company_charges(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/charges",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_company_insolvency(self, company_number: str) -> Dict[str, Any]:
        return self._get(f"/company/{company_number}/insolvency")

    def get_company_exemptions(self, company_number: str) -> Dict[str, Any]:
        return self._get(f"/company/{company_number}/exemptions")

    def get_company_registers(self, company_number: str) -> Dict[str, Any]:
        return self._get(f"/company/{company_number}/registers")

    def get_uk_establishments(
        self,
        company_number: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/company/{company_number}/uk-establishments",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    def get_officer_appointments(
        self,
        officer_id: str,
        items_per_page: int = 100,
        start_index: int = 0,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._get_all_pages(
            f"/officers/{officer_id}/appointments",
            item_key="items",
            items_per_page=items_per_page,
            start_index=start_index,
            max_items=max_items,
        )

    # ---------- helpers for aggregates ----------
    @staticmethod
    def _extract_officer_ids(
        officer_items: Iterable[Dict[str, Any]], hard_cap: int
    ) -> List[str]:
        """
        Extract officer IDs from officers list items robustly.
        """
        out: List[str] = []
        for it in officer_items:
            oid: Optional[str] = None

            if isinstance(it.get("officer_id"), str) and it["officer_id"]:
                oid = it["officer_id"]

            if not oid:
                links = it.get("links") or {}
                off = links.get("officer")
                if isinstance(off, dict):
                    ap = off.get("appointments")
                    if isinstance(ap, str) and "/officers/" in ap:
                        oid = ap.split("/officers/", 1)[-1].split("/", 1)[0]

            if not oid:
                links = it.get("links") or {}
                self_link = links.get("self")
                if isinstance(self_link, str) and "/officers/" in self_link:
                    oid = self_link.split("/officers/", 1)[-1].split("/", 1)[0]

            if oid and oid not in out:
                out.append(oid)
                if len(out) >= hard_cap:
                    break

        return out

    def get_company_full(
        self,
        company_number: str,
        max_filings: int = 500,
        max_officers: int = 500,
        max_psc: int = 500,
        max_charges: int = 500,
        max_uk_establishments: int = 500,
        enrich_officer_appointments: bool = False,
        max_appointments_per_officer: int = 200,
        max_officers_for_enrichment: int = 50,
    ) -> Dict[str, Any]:
        profile = self.get_company_profile(company_number)

        officers = self.get_company_officers(company_number, max_items=max_officers)
        filing_history = self.get_company_filing_history(
            company_number, max_items=max_filings
        )
        psc_ind = self.get_company_psc_individuals(company_number, max_items=max_psc)
        psc_corp = self.get_company_psc_corporate(company_number, max_items=max_psc)
        psc_legal = self.get_company_psc_legal_person(company_number, max_items=max_psc)
        psc_statements = self.get_company_psc_statements(
            company_number, max_items=max_psc
        )
        charges = self.get_company_charges(company_number, max_items=max_charges)

        # best-effort optional endpoints
        def _safe(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except CompaniesHouseError:
                return {"available": False, "note": "not found"}

        insolvency = _safe(self.get_company_insolvency, company_number)
        exemptions = _safe(self.get_company_exemptions, company_number)
        registers = _safe(self.get_company_registers, company_number)
        uk_establishments = self.get_uk_establishments(
            company_number, max_items=max_uk_establishments
        )

        appointments_by_officer_id: Dict[str, Dict[str, Any]] = {}
        if enrich_officer_appointments:
            unique_ids = self._extract_officer_ids(
                officers.get("items", []), hard_cap=max_officers_for_enrichment
            )
            for oid in unique_ids:
                try:
                    appts = self.get_officer_appointments(
                        oid, max_items=max_appointments_per_officer
                    )
                    appointments_by_officer_id[oid] = {
                        "items": appts.get("items", []),
                        "total_results": appts.get("total_results"),
                    }
                except CompaniesHouseError:
                    appointments_by_officer_id[oid] = {
                        "available": False,
                        "note": "not found",
                    }

        return {
            "profile": profile,
            "officers": {
                "items": officers.get("items", []),
                "appointments_by_officer_id": appointments_by_officer_id,
            },
            "filing_history": {"items": filing_history.get("items", [])},
            "psc": {
                "individual": psc_ind.get("items", []),
                "corporate_entity": psc_corp.get("items", []),
                "legal_person": psc_legal.get("items", []),
                "statements": psc_statements.get("items", []),
            },
            "charges": {"items": charges.get("items", [])},
            "insolvency": insolvency,
            "exemptions": exemptions,
            "registers": registers,
            "uk_establishments": {"items": uk_establishments.get("items", [])},
        }
