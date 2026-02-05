"""
Product Spec Generator API Routes
===================================

GET  /api/specs/{asin}        — returns cached or on-the-fly generated spec bundle.
GET  /api/specs/{asin}/export — Markdown export of spec bundle.
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/specs", tags=["Specs"])


class SpecBundleResponse(BaseModel):
    asin: str
    generated_at: Optional[str] = None
    version: str = "1.8"
    mapping_version: str = ""
    inputs_hash: str = ""
    run_id: Optional[str] = None
    improvement_score: float = 0.0
    reviews_analyzed: int = 0
    total_requirements: int = 0
    total_qc_tests: int = 0
    oem_spec_text: str = ""
    qc_checklist_text: str = ""
    rfq_message_text: str = ""
    bundle: Optional[Dict[str, Any]] = None


def _cached_to_response(asin: str, cached: dict) -> SpecBundleResponse:
    """Build response from a cached bundle dict."""
    return SpecBundleResponse(
        asin=asin,
        generated_at=cached["generated_at"],
        version=cached["version"],
        mapping_version=cached.get("mapping_version", ""),
        inputs_hash=cached.get("inputs_hash", ""),
        run_id=cached.get("run_id"),
        improvement_score=cached["improvement_score"],
        reviews_analyzed=cached["reviews_analyzed"],
        total_requirements=cached["total_requirements"],
        total_qc_tests=cached["total_qc_tests"],
        oem_spec_text=cached["oem_spec_text"],
        qc_checklist_text=cached["qc_checklist_text"],
        rfq_message_text=cached["rfq_message_text"],
        bundle=cached["bundle"],
    )


@router.get("/{asin}", response_model=SpecBundleResponse)
async def get_spec_bundle(
    asin: str,
    regenerate: bool = Query(False),
    run_id: Optional[str] = Query(None, description="Load spec from a specific pipeline run"),
):
    """
    Get the product spec bundle for an ASIN.

    Returns cached spec or generates on-the-fly from review data.
    Use ?regenerate=true to force fresh generation.
    Use ?run_id=UUID to load a specific version (reproducibility).
    """
    from . import db
    from ..specs import SpecGenerator

    generator = SpecGenerator()

    try:
        pool = db.get_pool()
        conn = pool.getconn()
        try:
            # Specific run_id requested — load that exact version
            if run_id:
                cached = generator.load_bundle_from_db(conn, asin, run_id=run_id)
                if not cached:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No spec bundle for ASIN {asin} with run_id {run_id}.",
                    )
                return _cached_to_response(asin, cached)

            # Try cached version first
            if not regenerate:
                cached = generator.load_bundle_from_db(conn, asin)
                if cached:
                    return _cached_to_response(asin, cached)

            # Generate from profile
            profile = _load_profile(conn, asin)
            if not profile:
                raise HTTPException(
                    status_code=404,
                    detail=f"No review data for ASIN {asin}. Run backfill first.",
                )

            bundle = generator.generate(profile)
            generator.save_bundle(conn, bundle)

            return SpecBundleResponse(
                asin=asin,
                generated_at=bundle.generated_at.isoformat(),
                version=bundle.version,
                mapping_version=bundle.mapping_version,
                inputs_hash=bundle.inputs_hash,
                improvement_score=bundle.improvement_score,
                reviews_analyzed=bundle.reviews_analyzed,
                total_requirements=bundle.oem_spec.total_requirements,
                total_qc_tests=len(bundle.qc_checklist.tests),
                oem_spec_text=bundle.oem_spec.rendered_text,
                qc_checklist_text=bundle.qc_checklist.rendered_text,
                rfq_message_text=bundle.rfq_message.body_text,
                bundle=bundle.to_dict(),
            )
        finally:
            pool.putconn(conn)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spec generation failed for {asin}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{asin}/export", response_class=PlainTextResponse)
async def export_spec_markdown(
    asin: str,
    run_id: Optional[str] = Query(None),
):
    """
    Export spec bundle as Markdown text.

    Ready to paste into Alibaba, email, or Notion.
    """
    from . import db
    from ..specs import SpecGenerator

    generator = SpecGenerator()

    try:
        pool = db.get_pool()
        conn = pool.getconn()
        try:
            cached = generator.load_bundle_from_db(conn, asin, run_id=run_id)
            if not cached:
                # Try generating on-the-fly
                profile = _load_profile(conn, asin)
                if not profile:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No spec data for ASIN {asin}.",
                    )
                bundle = generator.generate(profile)
                cached = {
                    "oem_spec_text": bundle.oem_spec.rendered_text,
                    "qc_checklist_text": bundle.qc_checklist.rendered_text,
                    "rfq_message_text": bundle.rfq_message.body_text,
                    "version": bundle.version,
                    "mapping_version": bundle.mapping_version,
                    "inputs_hash": bundle.inputs_hash,
                }

            md = f"""# Product Spec Bundle — {asin}

> Version: {cached.get('version', '1.8')} | Mapping: {cached.get('mapping_version', '')} | Hash: {cached.get('inputs_hash', '')}

---

## OEM Product Specification

```
{cached['oem_spec_text']}
```

---

## QC Inspection Checklist

```
{cached['qc_checklist_text']}
```

---

## RFQ Supplier Message

```
{cached['rfq_message_text']}
```
"""
            return PlainTextResponse(
                content=md,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="spec_{asin}.md"',
                },
            )
        finally:
            pool.putconn(conn)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spec export failed for {asin}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _load_profile(conn, asin: str):
    """Load or generate a ProductImprovementProfile for an ASIN."""
    from .shared import load_profile
    return load_profile(conn, asin)
