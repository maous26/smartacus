"""
Sourcing Quotes API Routes
==========================

Endpoints for managing supplier quotes.

Routes:
    POST   /api/sourcing/quotes         - Create a new quote
    GET    /api/sourcing/quotes/{asin}  - Get quotes for an ASIN
    PATCH  /api/sourcing/quotes/{id}    - Update a quote (e.g., mark inactive)
    GET    /api/sourcing/quotes/best/{asin} - Get best active quote for ASIN
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sourcing", tags=["sourcing"])


# ============================================================================
# MODELS
# ============================================================================

class QuoteCreate(BaseModel):
    """Request model for creating a quote."""
    asin: str = Field(..., min_length=10, max_length=20)
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None

    unit_price: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=10)
    unit_price_usd: Optional[float] = None  # Will be calculated if not provided for USD
    moq: Optional[int] = Field(default=None, ge=1)
    price_breaks: Optional[List[dict]] = None

    lead_time_days: Optional[int] = Field(default=None, ge=1)
    shipping_cost_usd: Optional[float] = Field(default=None, ge=0)
    incoterm: Optional[str] = Field(default=None, max_length=10)

    payment_terms: Optional[str] = None
    valid_until: Optional[datetime] = None

    source: Optional[str] = Field(default="manual", max_length=50)
    source_url: Optional[str] = None
    negotiation_notes: Optional[str] = None


class QuoteUpdate(BaseModel):
    """Request model for updating a quote."""
    is_active: Optional[bool] = None
    unit_price: Optional[float] = Field(default=None, gt=0)
    unit_price_usd: Optional[float] = None
    moq: Optional[int] = Field(default=None, ge=1)
    lead_time_days: Optional[int] = Field(default=None, ge=1)
    shipping_cost_usd: Optional[float] = Field(default=None, ge=0)
    payment_terms: Optional[str] = None
    valid_until: Optional[datetime] = None
    negotiation_notes: Optional[str] = None


class QuoteResponse(BaseModel):
    """Response model for a quote."""
    id: str
    asin: str
    supplier_name: Optional[str]
    unit_price: float
    currency: str
    unit_price_usd: Optional[float]
    moq: Optional[int]
    lead_time_days: Optional[int]
    shipping_cost_usd: Optional[float]
    incoterm: Optional[str]
    payment_terms: Optional[str]
    valid_until: Optional[datetime]
    source: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/quotes", response_model=QuoteResponse)
async def create_quote(quote: QuoteCreate):
    """Create a new supplier quote."""
    try:
        from . import db
        pool = db.get_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Calculate unit_price_usd if currency is USD and not provided
        unit_price_usd = quote.unit_price_usd
        if unit_price_usd is None and quote.currency.upper() == "USD":
            unit_price_usd = quote.unit_price

        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                # Verify ASIN exists
                cur.execute("SELECT 1 FROM asins WHERE asin = %s", (quote.asin,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail=f"ASIN {quote.asin} not found")

                # Validate valid_until is in future if provided
                if quote.valid_until and quote.valid_until < datetime.utcnow():
                    raise HTTPException(status_code=400, detail="valid_until must be in the future")

                cur.execute("""
                    INSERT INTO sourcing_quotes (
                        asin, supplier_name, supplier_contact,
                        unit_price, currency, unit_price_usd, moq, price_breaks,
                        lead_time_days, shipping_cost_usd, incoterm,
                        payment_terms, valid_until,
                        source, source_url, negotiation_notes
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s
                    )
                    RETURNING id, created_at
                """, (
                    quote.asin, quote.supplier_name, quote.supplier_contact,
                    quote.unit_price, quote.currency.upper(), unit_price_usd, quote.moq,
                    quote.price_breaks if quote.price_breaks else None,
                    quote.lead_time_days, quote.shipping_cost_usd, quote.incoterm,
                    quote.payment_terms, quote.valid_until,
                    quote.source, quote.source_url, quote.negotiation_notes,
                ))
                row = cur.fetchone()
                conn.commit()

                return QuoteResponse(
                    id=str(row[0]),
                    asin=quote.asin,
                    supplier_name=quote.supplier_name,
                    unit_price=quote.unit_price,
                    currency=quote.currency.upper(),
                    unit_price_usd=unit_price_usd,
                    moq=quote.moq,
                    lead_time_days=quote.lead_time_days,
                    shipping_cost_usd=quote.shipping_cost_usd,
                    incoterm=quote.incoterm,
                    payment_terms=quote.payment_terms,
                    valid_until=quote.valid_until,
                    source=quote.source,
                    is_active=True,
                    created_at=row[1],
                )
        finally:
            pool.putconn(conn)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotes/{asin}", response_model=List[QuoteResponse])
async def get_quotes(
    asin: str,
    active_only: bool = Query(default=True, description="Only return active quotes"),
    valid_only: bool = Query(default=True, description="Only return non-expired quotes"),
):
    """Get all quotes for an ASIN."""
    try:
        from . import db
        pool = db.get_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT id, asin, supplier_name, unit_price, currency, unit_price_usd,
                           moq, lead_time_days, shipping_cost_usd, incoterm,
                           payment_terms, valid_until, source, is_active, created_at
                    FROM sourcing_quotes
                    WHERE asin = %s
                """
                params = [asin]

                if active_only:
                    query += " AND is_active = true"
                if valid_only:
                    query += " AND (valid_until IS NULL OR valid_until > NOW())"

                query += " ORDER BY unit_price_usd ASC NULLS LAST, created_at DESC"

                cur.execute(query, params)
                rows = cur.fetchall()

                return [
                    QuoteResponse(
                        id=str(row[0]),
                        asin=row[1],
                        supplier_name=row[2],
                        unit_price=float(row[3]),
                        currency=row[4],
                        unit_price_usd=float(row[5]) if row[5] else None,
                        moq=row[6],
                        lead_time_days=row[7],
                        shipping_cost_usd=float(row[8]) if row[8] else None,
                        incoterm=row[9],
                        payment_terms=row[10],
                        valid_until=row[11],
                        source=row[12],
                        is_active=row[13],
                        created_at=row[14],
                    )
                    for row in rows
                ]
        finally:
            pool.putconn(conn)

    except Exception as e:
        logger.error(f"Failed to get quotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotes/best/{asin}", response_model=Optional[QuoteResponse])
async def get_best_quote(asin: str):
    """Get the best (lowest unit_price_usd) active and valid quote for an ASIN."""
    try:
        from . import db
        pool = db.get_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, asin, supplier_name, unit_price, currency, unit_price_usd,
                           moq, lead_time_days, shipping_cost_usd, incoterm,
                           payment_terms, valid_until, source, is_active, created_at
                    FROM sourcing_quotes
                    WHERE asin = %s
                      AND is_active = true
                      AND (valid_until IS NULL OR valid_until > NOW())
                      AND unit_price_usd IS NOT NULL
                    ORDER BY unit_price_usd ASC
                    LIMIT 1
                """, (asin,))
                row = cur.fetchone()

                if not row:
                    return None

                return QuoteResponse(
                    id=str(row[0]),
                    asin=row[1],
                    supplier_name=row[2],
                    unit_price=float(row[3]),
                    currency=row[4],
                    unit_price_usd=float(row[5]) if row[5] else None,
                    moq=row[6],
                    lead_time_days=row[7],
                    shipping_cost_usd=float(row[8]) if row[8] else None,
                    incoterm=row[9],
                    payment_terms=row[10],
                    valid_until=row[11],
                    source=row[12],
                    is_active=row[13],
                    created_at=row[14],
                )
        finally:
            pool.putconn(conn)

    except Exception as e:
        logger.error(f"Failed to get best quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/quotes/{quote_id}", response_model=QuoteResponse)
async def update_quote(quote_id: str, update: QuoteUpdate):
    """Update a quote (e.g., mark as inactive, update price)."""
    try:
        from . import db
        pool = db.get_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Build SET clause dynamically
        updates = []
        params = []
        for field, value in update.model_dump(exclude_unset=True).items():
            if value is not None:
                updates.append(f"{field} = %s")
                params.append(value)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                params.append(quote_id)
                cur.execute(f"""
                    UPDATE sourcing_quotes
                    SET {', '.join(updates)}
                    WHERE id = %s
                    RETURNING id, asin, supplier_name, unit_price, currency, unit_price_usd,
                              moq, lead_time_days, shipping_cost_usd, incoterm,
                              payment_terms, valid_until, source, is_active, created_at
                """, params)
                row = cur.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="Quote not found")

                conn.commit()

                return QuoteResponse(
                    id=str(row[0]),
                    asin=row[1],
                    supplier_name=row[2],
                    unit_price=float(row[3]),
                    currency=row[4],
                    unit_price_usd=float(row[5]) if row[5] else None,
                    moq=row[6],
                    lead_time_days=row[7],
                    shipping_cost_usd=float(row[8]) if row[8] else None,
                    incoterm=row[9],
                    payment_terms=row[10],
                    valid_until=row[11],
                    source=row[12],
                    is_active=row[13],
                    created_at=row[14],
                )
        finally:
            pool.putconn(conn)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))
