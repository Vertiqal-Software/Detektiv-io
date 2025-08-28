# app/services/ch_client.py
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Dict, Optional

import httpx

API_BASE = "https://api.company-information.service.gov.uk"


class CompaniesHouseClient:
    """
    Minimal async client for Companies House REST API.

    Notes:
    - Auth is HTTP Basic where the API key is the username and password is empty.
    - Keeps a persistent httpx.AsyncClient; call `await aclose()` when done.
    - Retries 429 and 5xx with capped exponential backoff, honors Retry-After.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 8.0):
        self.api_key = api_key or os.getenv("CH_API_KEY")
        # httpx.Timeout can be a float or per-phase config; a single float applies to connect/read/write
        self.timeout = httpx.Timeout(timeout)
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "User-Agent": "detecktiv.io/preview (+contact: support@detecktiv.io)",
                "Accept": "application/json",
            },
        )

    # ---------- internal helpers ----------

    def _auth_headers(self) -> Dict[str, str]:
        """
        Companies House uses Basic auth where the API key is the username and the password is empty.
        """
        if not self.api_key:
            return {}
        token = base64.b64encode((self.api_key + ":").encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def _get(self, path: str, params: Optional[dict] = None) -> Dict[str, Any]:
        """
        GET with simple retry policy:
        - 429: respect Retry-After (seconds) if present, otherwise backoff
        - 5xx: exponential backoff
        - 401: raise immediately with a clear message
        """
        url = f"{API_BASE}{path}"
        params = params or {}
        max_attempts = 5
        backoff = 0.5  # seconds
        for attempt in range(max_attempts):
            resp = await self._client.get(
                url, params=params, headers=self._auth_headers()
            )
            status = resp.status_code

            # Unauthorized -> don't retry
            if status == 401:
                # Raise an HTTPStatusError with a useful message
                raise httpx.HTTPStatusError(
                    "Unauthorized (check CH_API_KEY)",
                    request=resp.request,
                    response=resp,
                )

            # Too Many Requests -> respect Retry-After if present
            if status == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(0.0, float(retry_after))
                        await asyncio.sleep(delay)
                    except Exception:
                        # Fallback to backoff if header is weird
                        await asyncio.sleep(backoff)
                else:
                    await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue

            # Server errors -> retry with backoff
            if 500 <= status < 600:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 8.0)
                    continue

            # Raise on other non-2xx statuses
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                # bubble up with original context
                raise e

            # Parse JSON body
            try:
                return resp.json()
            except ValueError as e:
                raise httpx.HTTPError(f"Invalid JSON from {url}: {e}") from e

        raise httpx.HTTPError(f"Failed to GET {path} after retries")

    # ---------- public endpoints ----------

    async def company_profile(self, company_number: str) -> Dict[str, Any]:
        return await self._get(f"/company/{company_number}")

    async def officers(self, company_number: str) -> Dict[str, Any]:
        return await self._get(f"/company/{company_number}/officers")

    async def psc(self, company_number: str) -> Dict[str, Any]:
        return await self._get(
            f"/company/{company_number}/persons-with-significant-control"
        )

    async def filing_history(
        self, company_number: str, items_per_page: int = 100
    ) -> Dict[str, Any]:
        return await self._get(
            f"/company/{company_number}/filing-history",
            {"items_per_page": items_per_page},
        )

    # ---------- lifecycle ----------

    async def aclose(self) -> None:
        await self._client.aclose()

    # Optional convenience for async with:
    async def __aenter__(self) -> "CompaniesHouseClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()
