# app/api/companies.py
"""
Companies API endpoints - Simple SQLite implementation for MVP.
"""
from __future__ import annotations

import sqlite3
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(
    prefix="/companies",
    tags=["companies"]
)

class CompanyResponse(BaseModel):
    id: int
    name: str
    website: Optional[str] = None
    description: Optional[str] = None
    created_at: str
    updated_at: str

class CompanyCreate(BaseModel):
    name: str
    website: Optional[str] = None
    description: Optional[str] = None

def get_db_connection():
    """Get SQLite database connection"""
    return sqlite3.connect('test.db')

@router.get("/", response_model=List[CompanyResponse])
def list_companies():
    """List all companies"""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM companies ORDER BY name")
        companies = cursor.fetchall()
        conn.close()
        
        return [dict(company) for company in companies]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/", response_model=CompanyResponse)
def create_company(company: CompanyCreate):
    """Create a new company"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO companies (name, website, description) VALUES (?, ?, ?)",
            (company.name, company.website, company.description)
        )
        company_id = cursor.lastrowid
        conn.commit()
        
        # Get the created company
        cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, result))
        else:
            raise HTTPException(status_code=404, detail="Created company not found")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/{company_id}", response_model=CompanyResponse)  
def get_company(company_id: int):
    """Get a company by ID"""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        company = cursor.fetchone()
        conn.close()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
            
        return dict(company)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")