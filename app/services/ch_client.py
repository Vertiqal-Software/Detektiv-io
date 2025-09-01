# app/services/ch_client.py
from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any, AsyncGenerator, Dict, Iterable, Optional

import httpx

DEFAULT_BASE = "https://api.company-information.service.gov.uk"


class CompaniesHouseClient:
    """
    Async Companies House API client (httpx) with:
      - HTTP Basic Auth (API key as username, blank password)
      - Connection pooling via httpx.AsyncClient
      - Token-bucket rate limiting (defaults align with ~600 req / 5 min)
      - Retries with capped exponential backoff + jitter for 429/5xx, honors Retry-After
      - Clear errors and robust JSON handling

    ENV (all optional except the API key in prod):
      - COMPANIES_HOUSE_API_KEY or CH_API_KEY : API key (username in Basic auth)
      - CH_BASE_URL                           : override base URL (default: official API)
      - CH_TIMEOUT_SECONDS                    : float seconds (default 10.0)
      - CH_BURST_CAPACITY                     : int tokens in bucket (default 60)
      - CH_REFILL_PER_SECOND                  : float tokens/sec (default 600/300 = 2/sec)
      - CH_MAX_RETRIES                        : int (default 3), for 429/5xx
      - CH_USER_AGENT                         : custom UA string

    Usage:
        async with CompaniesHouseClient() as ch:
            data = await ch.company_profile("01234567")
            # or search:
            async for item in ch.iter_search("acme", items_per_page=25, max_items=100):
                ...
    """

    # -------------------- Rate limiter (token bucket) --------------------
    class _TokenBucket:
        def __init__(self, capacity: int, refill_per_second: float) -> None:
            self.capacity = max(1, int(capacity))
            self.refill_per_second = float(refill_per_second)
            self._tokens: float = float(self.capacity)
            self._ts: float = time.monotonic()
            self._lock = asyncio.Lock()

        def _refill_no_lock(self) -> None:
            now = time.monotonic()
            elapsed = now - self._ts
            if elapsed > 0:
                self._tokens = min(
                    self.capacity, self._tokens + elapsed * self.refill_per_second
                )
                self._ts = now

        async def consume(
            self, tokens: float = 1.0, *, block: bool = True, max_wait: float = 30.0
        ) -> bool:
            """
            Consume tokens from the bucket. If block=True, wait up to max_wait seconds.
            Returns True on success, False if not enough tokens by the deadline.
            """
            deadline = time.monotonic() + max_wait
            while True:
                async with self._lock:
                    self._refill_no_lock()
                    if self._tokens >= tokens:
                        self._tokens -= tokens
                        return True
                    need = tokens - self._tokens
                    wait = (
                        need / self.refill_per_second
                        if self.refill_per_second > 0
                        else max_wait
                    )
                    wait = max(0.01, min(wait, max_wait))
                if not block or time.monotonic() + wait > deadline:
                    return False
                await asyncio.sleep(wait)

    # -------------------- Init / config --------------------
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float | httpx.Timeout = 10.0,
        burst_capacity: Optional[int] = None,
        refill_per_second: Optional[float] = None,
        max_retries: Optional[int] = None,
        user_agent: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        # API key (support both env names)
        self.api_key = (
            api_key
            or os.getenv("COMPANIES_HOUSE_API_KEY")
            or os.getenv("CH_API_KEY")
            or ""
        ).strip()
        self.base_url = (base_url or os.getenv("CH_BASE_URL") or DEFAULT_BASE).rstrip(
            "/"
        )
        self.timeout = (
            httpx.Timeout(float(os.getenv("CH_TIMEOUT_SECONDS", "10.0")))
            if isinstance(timeout, (int, float))
            else timeout
        )
        self.burst_capacity = int(
            os.getenv("CH_BURST_CAPACITY", str(burst_capacity or 60))
        )
        self.refill_per_second = float(
            os.getenv("CH_REFILL_PER_SECOND", str(refill_per_second or (600.0 / 300.0)))
        )
        self.max_retries = int(os.getenv("CH_MAX_RETRIES", str(max_retries or 3)))
        self.user_agent = (
            user_agent
            or os.getenv("CH_USER_AGENT")
            or "detecktiv.io/1.0 (+https://detecktiv.io)"
        ).strip()

        # httpx client (pooled connections)
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )

        # process-wide limiter (per-instance here; lift to a shared static if you want global limits)
        self._bucket = self._TokenBucket(
            capacity=self.burst_capacity, refill_per_second=self.refill_per_second
        )

    # -------------------- Lifecycle --------------------
    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "CompaniesHouseClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    # -------------------- Internal helpers --------------------
    def _auth_headers(self) -> Dict[str, str]:
        """
        Companies House uses Basic auth where the API key is the username and the password is empty.
        """
        if not self.api_key:
            # Allow running without key in dev, but real endpoints will 401.
            return {}
        token = base64.b64encode((self.api_key + ":").encode()).decode()
        return {"Authorization": f"Basic {token}"}

    @staticmethod
    def _compute_backoff(attempt: int, base: float = 0.5, cap: float = 8.0) -> float:
        """
        Exponential backoff with jitter: base * 2^(attempt-1) +/- 20%, capped.
        """
        raw = base * (2 ** max(0, attempt - 1))
        # cheap jitter using monotonic fractional part
        frac = time.monotonic() % 1.0
        jitter = raw * (0.4 * (frac - 0.5))  # +/- 20%
        return max(0.1, min(cap, raw + jitter))

    @staticmethod
    def _retry_after_delay(resp: httpx.Response, default: float) -> float:
        ra = resp.headers.get("Retry-After")
        if not ra:
            return default
        try:
            # seconds form (Companies House commonly uses seconds)
            sec = float(ra)
            return max(0.1, min(60.0, sec))
        except Exception:
            return default

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        require_key: bool = True,
    ) -> httpx.Response:
        """
        Low-level request with:
          - token bucket rate limiting
          - retries for 429/5xx with backoff, honoring Retry-After
          - immediate fail on 401 (bad key) and 403
        """
        # Rate limit before firing the request
        if not await self._bucket.consume(block=True, max_wait=30.0):
            raise httpx.HTTPError("Local CH rate limiter exhausted; please retry later")

        # Missing API key in prod-like calls
        if require_key and not self.api_key:
            # You can pass require_key=False for public, unauthenticated endpoints (none in CH core)
            raise httpx.HTTPError("COMPANIES_HOUSE_API_KEY / CH_API_KEY is required")

        headers = self._auth_headers()
        url = f"{self.base_url}{path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.request(
                    method,
                    url,
                    params=params or {},
                    json=json,
                    headers=headers,
                )
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout):
                if attempt <= self.max_retries:
                    await asyncio.sleep(self._compute_backoff(attempt))
                    continue
                raise httpx.HTTPError("Companies House request timed out")
            except httpx.HTTPError:
                # network errors -> retry a few times
                if attempt <= self.max_retries:
                    await asyncio.sleep(self._compute_backoff(attempt))
                    continue
                raise

            status = resp.status_code

            # Immediate auth errors (no retries)
            if status in (401, 403):
                # Include a friendlier message
                msg = "Unauthorized (check API key)" if status == 401 else "Forbidden"
                raise httpx.HTTPStatusError(msg, request=resp.request, response=resp)

            # 429: honor Retry-After or backoff
            if status == 429:
                if attempt <= self.max_retries:
                    delay = self._retry_after_delay(
                        resp, self._compute_backoff(attempt)
                    )
                    await asyncio.sleep(delay)
                    continue
                raise httpx.HTTPStatusError(
                    "Rate limited by Companies House",
                    request=resp.request,
                    response=resp,
                )

            # 5xx: retry with backoff
            if 500 <= status < 600:
                if attempt <= self.max_retries:
                    await asyncio.sleep(self._compute_backoff(attempt))
                    continue
                raise httpx.HTTPStatusError(
                    f"Companies House server error {status}",
                    request=resp.request,
                    response=resp,
                )

            # Other non-2xx -> raise
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                # Bubble up original context
                raise

            return resp

    async def _get(self, path: str, params: Optional[dict] = None) -> Dict[str, Any]:
        resp = await self._request("GET", path, params=params)
        try:
            return resp.json()
        except ValueError as e:
            raise httpx.HTTPError(f"Invalid JSON from {resp.request.url!s}: {e}") from e

    # -------------------- Public endpoints (company-centric) --------------------
    async def company_profile(self, company_number: str) -> Dict[str, Any]:
        company_number = (company_number or "").strip()
        if not company_number:
            raise ValueError("company_number is required")
        return await self._get(f"/company/{company_number}")

    async def officers(self, company_number: str) -> Dict[str, Any]:
        company_number = (company_number or "").strip()
        if not company_number:
            raise ValueError("company_number is required")
        return await self._get(f"/company/{company_number}/officers")

    async def psc(self, company_number: str) -> Dict[str, Any]:
        company_number = (company_number or "").strip()
        if not company_number:
            raise ValueError("company_number is required")
        return await self._get(
            f"/company/{company_number}/persons-with-significant-control"
        )

    async def filing_history(
        self, company_number: str, items_per_page: int = 100
    ) -> Dict[str, Any]:
        company_number = (company_number or "").strip()
        if not company_number:
            raise ValueError("company_number is required")
        if items_per_page < 1 or items_per_page > 200:
            raise ValueError("items_per_page must be between 1 and 200")
        return await self._get(
            f"/company/{company_number}/filing-history",
            {"items_per_page": items_per_page},
        )

    # -------------------- Search endpoints --------------------
    async def search_companies(
        self, query: str, *, items_per_page: int = 20, start_index: int = 0
    ) -> Dict[str, Any]:
        """
        GET /search/companies?q=...&items_per_page=...&start_index=...
        Returns the raw Companies House search JSON.
        """
        q = (query or "").strip()
        if not q:
            raise ValueError("query is required")
        if items_per_page < 1 or items_per_page > 100:
            raise ValueError("items_per_page must be between 1 and 100")
        if start_index < 0:
            raise ValueError("start_index must be >= 0")
        return await self._get(
            "/search/companies",
            {"q": q, "items_per_page": items_per_page, "start_index": start_index},
        )

    async def iter_search(
        self,
        query: str,
        *,
        items_per_page: int = 20,
        max_items: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async generator over search results (yields items).
        Stops after `max_items` if provided, or when no more pages are available.
        """
        fetched = 0
        start = 0
        while True:
            page = await self.search_companies(
                query, items_per_page=items_per_page, start_index=start
            )
            items: Iterable[Dict[str, Any]] = page.get("items") or []
            count = 0
            for item in items:
                yield item
                count += 1
                fetched += 1
                if max_items is not None and fetched >= max_items:
                    return
            if count < items_per_page:
                return  # no more pages
            start += items_per_page
