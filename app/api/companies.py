# app/api/companies.py

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db.main import get_engine

router = APIRouter()


# ----- Schemas ---------------------------------------------------------------


class CompanyCreate(BaseModel):
    name: str
    website: Optional[str] = None


class CompanyOut(BaseModel):
    id: int
    name: str
    website: Optional[str] = None
    # Keep this as str to match the OpenAPI schema & tests
    created_at: str


# ----- Helpers ---------------------------------------------------------------


def _row_to_company_out(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a DB row mapping into the response schema, ensuring created_at is a string."""
    data = dict(row)
    ca = data.get("created_at")
    if isinstance(ca, datetime):
        data["created_at"] = ca.isoformat()
    elif ca is None:
        # Shouldn't happen (DB default), but keep the contract
        data["created_at"] = datetime.utcnow().isoformat() + "Z"
    return data


# ----- Routes ----------------------------------------------------------------


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(payload: CompanyCreate) -> CompanyOut:
    """
    Create a company. Enforces unique name at the DB layer.
    Returns the created row (id, name, website, created_at).
    """
    sql = text(
        """
        INSERT INTO companies (name, website)
        VALUES (:name, :website)
        RETURNING id, name, website, created_at
        """
    )
    engine = get_engine()
    try:
        with engine.begin() as conn:
            row = (
                conn.execute(sql, {"name": payload.name, "website": payload.website})
                .mappings()
                .one()
            )
            return _row_to_company_out(row)  # type: ignore[return-value]
    except IntegrityError as e:
        # Unique-violation -> 409
        # (SQLSTATE 23505 is the standard code, but we keep it simple/robust here.)
        raise HTTPException(
            status_code=409, detail="Company name already exists"
        ) from e


@router.get("/companies", response_model=List[CompanyOut])
def list_companies(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> List[CompanyOut]:
    """
    List companies with simple pagination.
    """
    sql = text(
        """
        SELECT id, name, website, created_at
        FROM companies
        ORDER BY id
        LIMIT :limit OFFSET :offset
        """
    )
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit, "offset": offset}).mappings().all()
        return [_row_to_company_out(r) for r in rows]  # type: ignore[return-value]
