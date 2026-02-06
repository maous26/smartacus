#!/usr/bin/env python3
"""
Smartacus Controlled Pipeline Runner — Run 1
=============================================

Phase 0 (Pre-flight) + Phase 1 (Controlled Ingestion) in a single script.

Protocol:
    - FREEZE MODE: score everything, promote nothing to shortlist
    - MAX_ASINS = 100: blast radius limited
    - AUDIT MODE: full pipeline_runs tracking, data quality gates, scoring artifacts
    - Every step logged with timing

Usage:
    python scripts/run_controlled.py                    # Full Run 1
    python scripts/run_controlled.py --max-asins 10     # Quick smoke test
    python scripts/run_controlled.py --skip-discovery   # Use ASINs already in DB
    python scripts/run_controlled.py --verbose           # Debug logging

Environment:
    Reads from .env (KEEPA_API_KEY, DATABASE_*, INGESTION_*)
"""

import os
import sys
import json
import uuid
import time
import logging
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(verbose: bool = False, log_file: str = None):
    """Configure logging with optional file output."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    # Suppress noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("keepa").setLevel(logging.WARNING)

logger = logging.getLogger("smartacus.controlled_run")


# ============================================================================
# HELPERS
# ============================================================================

class RunAudit:
    """Collects all audit data for the controlled run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.timings: Dict[str, float] = {}
        self.counts: Dict[str, int] = {}
        self.errors: List[Dict] = []
        self.scoring_results: List[Dict] = []
        self.data_quality: Dict[str, Any] = {}
        self.warnings: List[str] = []

    def time_phase(self, name: str):
        """Context manager to time a phase."""
        return PhaseTimer(self, name)

    def record_count(self, key: str, value: int):
        self.counts[key] = value

    def record_error(self, asin: str, error_type: str, message: str):
        self.errors.append({
            "asin": asin,
            "type": error_type,
            "message": str(message)[:200],
            "timestamp": datetime.utcnow().isoformat(),
        })

    def warn(self, msg: str):
        self.warnings.append(msg)
        logger.warning(msg)

    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timings_ms": {k: int(v * 1000) for k, v in self.timings.items()},
            "counts": self.counts,
            "errors_count": len(self.errors),
            "errors_sample": self.errors[:10],
            "data_quality": self.data_quality,
            "warnings": self.warnings,
            "scoring_distribution": self._scoring_distribution(),
        }

    def _scoring_distribution(self) -> Dict[str, int]:
        """Distribution of final scores by bucket."""
        buckets = {"0-19": 0, "20-39": 0, "40-59": 0, "60-79": 0, "80-100": 0, "rejected": 0}
        for r in self.scoring_results:
            score = r.get("final_score", 0)
            is_valid = r.get("is_valid", True)
            if not is_valid:
                buckets["rejected"] += 1
            elif score < 20:
                buckets["0-19"] += 1
            elif score < 40:
                buckets["20-39"] += 1
            elif score < 60:
                buckets["40-59"] += 1
            elif score < 80:
                buckets["60-79"] += 1
            else:
                buckets["80-100"] += 1
        return buckets


class PhaseTimer:
    """Context manager for timing pipeline phases."""
    def __init__(self, audit: RunAudit, name: str):
        self.audit = audit
        self.name = name
        self.start = None

    def __enter__(self):
        self.start = time.monotonic()
        logger.info(f"--- Phase: {self.name} ---")
        return self

    def __exit__(self, *args):
        elapsed = time.monotonic() - self.start
        self.audit.timings[self.name] = elapsed
        logger.info(f"    {self.name}: {elapsed:.1f}s")


def compute_time_signals(product) -> Dict[str, float]:
    """
    Extract time signals from ProductData for the economic scorer.

    Uses price_history and bsr_history to compute:
    - stockout_frequency: estimated from gaps in price data
    - seller_churn_90d: estimated from seller count changes
    - price_volatility: coefficient of variation over 90 days
    - bsr_acceleration: 2nd derivative proxy from BSR history
    - estimated_monthly_units: rough estimate from BSR
    """
    signals = {
        "stockout_frequency": 0.0,
        "seller_churn_90d": 0.0,
        "price_volatility": 0.0,
        "bsr_acceleration": 0.0,
        "estimated_monthly_units": 50,
    }

    snap = product.current_snapshot

    # --- Price volatility from history ---
    if product.price_history and len(product.price_history) >= 5:
        prices = [float(p.price_usd) for p in product.price_history if float(p.price_usd) > 0]
        if prices:
            mean_price = sum(prices) / len(prices)
            if mean_price > 0:
                variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
                std_dev = variance ** 0.5
                signals["price_volatility"] = std_dev / mean_price

            # Stockout proxy: count price gaps > 2 days in 90 days
            sorted_history = sorted(product.price_history, key=lambda p: p.timestamp)
            gaps = 0
            for i in range(1, len(sorted_history)):
                delta = (sorted_history[i].timestamp - sorted_history[i-1].timestamp).total_seconds()
                if delta > 172800:  # > 2 days gap = potential stockout
                    gaps += 1
            signals["stockout_frequency"] = gaps / 3.0  # normalize to per-month

    # --- BSR acceleration from history ---
    if product.bsr_history and len(product.bsr_history) >= 10:
        sorted_bsr = sorted(product.bsr_history, key=lambda b: b.timestamp)
        n = len(sorted_bsr)
        mid = n // 2

        # First half average vs second half average
        first_half_avg = sum(b.bsr for b in sorted_bsr[:mid]) / mid
        second_half_avg = sum(b.bsr for b in sorted_bsr[mid:]) / (n - mid)

        if first_half_avg > 0:
            # Negative means improving (BSR going down)
            bsr_change = (second_half_avg - first_half_avg) / first_half_avg
            signals["bsr_acceleration"] = -bsr_change  # Invert: positive = improving

    # --- Monthly units estimate from BSR ---
    bsr = snap.bsr_primary
    if bsr and bsr > 0:
        # Rough heuristic: BSR → monthly units
        if bsr < 1000:
            signals["estimated_monthly_units"] = 300
        elif bsr < 5000:
            signals["estimated_monthly_units"] = 150
        elif bsr < 20000:
            signals["estimated_monthly_units"] = 80
        elif bsr < 50000:
            signals["estimated_monthly_units"] = 40
        elif bsr < 100000:
            signals["estimated_monthly_units"] = 20
        else:
            signals["estimated_monthly_units"] = 10

    # --- Seller churn proxy ---
    # Without historical seller counts, use a heuristic based on seller count
    seller_count = snap.seller_count or 5
    if seller_count > 15:
        signals["seller_churn_90d"] = 0.25  # High competition = more churn
    elif seller_count > 8:
        signals["seller_churn_90d"] = 0.15
    elif seller_count > 3:
        signals["seller_churn_90d"] = 0.10
    else:
        signals["seller_churn_90d"] = 0.05

    return signals


def product_to_scorer_input(product) -> Dict[str, Any]:
    """
    Convert ProductData to the dict format expected by OpportunityScorer.score().

    Maps snapshot data to scorer fields. Uses conservative defaults
    for fields we can't get from Keepa (e.g., alibaba_price estimated
    as amazon_price / 5).
    """
    snap = product.current_snapshot
    amazon_price = float(snap.price_current) if snap.price_current else 0

    # BSR deltas from history
    bsr_delta_7d = 0.0
    bsr_delta_30d = 0.0

    if product.bsr_history and len(product.bsr_history) >= 2:
        sorted_bsr = sorted(product.bsr_history, key=lambda b: b.timestamp)
        now = datetime.utcnow()

        # 7-day delta
        recent_7d = [b for b in sorted_bsr if b.timestamp >= now - timedelta(days=7)]
        if len(recent_7d) >= 2 and recent_7d[0].bsr > 0:
            bsr_delta_7d = (recent_7d[-1].bsr - recent_7d[0].bsr) / recent_7d[0].bsr

        # 30-day delta
        recent_30d = [b for b in sorted_bsr if b.timestamp >= now - timedelta(days=30)]
        if len(recent_30d) >= 2 and recent_30d[0].bsr > 0:
            bsr_delta_30d = (recent_30d[-1].bsr - recent_30d[0].bsr) / recent_30d[0].bsr

    # Price trend from history
    price_trend_30d = 0.0
    if product.price_history and len(product.price_history) >= 2:
        sorted_prices = sorted(product.price_history, key=lambda p: p.timestamp)
        now = datetime.utcnow()
        recent_prices = [p for p in sorted_prices if p.timestamp >= now - timedelta(days=30)]
        if len(recent_prices) >= 2:
            first_price = float(recent_prices[0].price_usd)
            last_price = float(recent_prices[-1].price_usd)
            if first_price > 0:
                price_trend_30d = (last_price - first_price) / first_price

    return {
        "product_id": product.asin,
        "amazon_price": amazon_price,
        "alibaba_price": amazon_price / 5,  # Conservative estimate
        "shipping_per_unit": 3.00,
        "bsr_current": snap.bsr_primary or 999999,
        "bsr_delta_7d": bsr_delta_7d,
        "bsr_delta_30d": bsr_delta_30d,
        "reviews_per_month": (snap.review_count or 0) / 12,  # Rough proxy
        "seller_count": snap.seller_count or 10,
        "buybox_rotation": 0.15,  # Default — Keepa doesn't give this directly
        "review_gap_vs_top10": 0.50,  # Default — would need category analysis
        "negative_review_percent": 0.10,  # Default
        "wish_mentions_per_100": 3,  # Default
        "unanswered_questions": 5,  # Default
        "stockout_count_90d": 0,  # Will be computed from history
        "price_trend_30d": price_trend_30d,
        "seller_churn_90d": 0,
        "bsr_acceleration": 0.0,
    }


def _generate_action(window_days: int) -> str:
    """Generate action recommendation based on window."""
    if window_days <= 14:
        return "ACTION IMMEDIATE: Sourcer fournisseur cette semaine"
    elif window_days <= 30:
        return "PRIORITAIRE: Lancer analyse fournisseurs sous 7 jours"
    elif window_days <= 60:
        return "ACTIF: Planifier sourcing dans les 2 semaines"
    else:
        return "SURVEILLER: Ajouter au backlog, reevaluer dans 30 jours"


# ============================================================================
# MAIN CONTROLLED RUN
# ============================================================================

def run_controlled(
    max_asins: int = 100,
    skip_discovery: bool = False,
    skip_filter: bool = False,
    verbose: bool = False,
    explicit_asins: Optional[List[str]] = None,
):
    """
    Execute a controlled pipeline run with full audit trail.

    Phase 0: Pre-flight checks
    Phase 1: Discovery → Fetch → Insert → Score → Audit
    """
    from src.data import IngestionPipeline, KeepaClient, KeepaAPIError
    from src.scoring import EconomicScorer
    # Import db module directly to avoid FastAPI dependency via src.api.__init__
    import importlib.util
    db_spec = importlib.util.spec_from_file_location("db", project_root / "src" / "api" / "db.py")
    db = importlib.util.module_from_spec(db_spec)
    db_spec.loader.exec_module(db)

    run_id = str(uuid.uuid4())[:12]
    session_id = str(uuid.uuid4())
    audit = RunAudit(run_id)
    start_time = time.monotonic()

    print()
    print("=" * 70)
    print(f"  SMARTACUS CONTROLLED RUN — {run_id}")
    print(f"  Mode: FREEZE (score only, no shortlist promotion)")
    print(f"  Max ASINs: {max_asins}")
    print(f"  Started: {datetime.utcnow().isoformat()}Z")
    print("=" * 70)
    print()

    # ==================================================================
    # PHASE 0: PRE-FLIGHT
    # ==================================================================
    print("[PHASE 0] PRE-FLIGHT CHECKS")
    print("-" * 40)

    # 0a. Create pipeline_run record in DB
    pipeline_run_id = None
    try:
        db_pool = db.get_pool()
        if db_pool:
            pipeline_run_id = db.create_pipeline_run(
                triggered_by="controlled_run_v1",
                config_snapshot={
                    "run_id": run_id,
                    "max_asins": max_asins,
                    "freeze_mode": True,
                    "skip_discovery": skip_discovery,
                    "skip_filter": skip_filter,
                },
            )
            if pipeline_run_id:
                print(f"  [OK] Pipeline run created: {pipeline_run_id[:8]}...")
                db.update_pipeline_run(pipeline_run_id, status="running")
            else:
                audit.warn("Failed to create pipeline_run record — continuing without tracking")
        else:
            audit.warn("DB pool not available — continuing without pipeline tracking")
    except Exception as e:
        audit.warn(f"DB init failed: {e}")

    # 0b. Check Keepa API
    try:
        from src.data.config import get_settings
        settings = get_settings()
        print(f"  [OK] Config loaded: category={settings.ingestion.category_node_id}")
    except Exception as e:
        print(f"  [FAIL] Config error: {e}")
        return 1

    # 0c. Initialize pipeline
    try:
        pipeline = IngestionPipeline()
        tokens_before = pipeline.keepa.get_tokens_left()
        print(f"  [OK] Keepa connected: {tokens_before} tokens available")

        # Estimate tokens needed: discovery(~5) + products(~2 per ASIN)
        tokens_needed = 5 + (max_asins * 2)
        print(f"  [..] Tokens needed (estimate): ~{tokens_needed}")
        print(f"  [..] Keepa library will auto-wait for tokens (wait=True)")
        print(f"       At ~1 token/min, budget: ~{tokens_needed} minutes max")

    except Exception as e:
        print(f"  [FAIL] Pipeline init failed: {e}")
        if pipeline_run_id:
            db.update_pipeline_run(pipeline_run_id, status="failed", error_message=str(e))
        return 1

    scorer = EconomicScorer()
    print(f"  [OK] Scorer initialized")
    print(f"  [OK] FREEZE MODE active — no shortlist promotion")
    print()

    # ==================================================================
    # PHASE 1: CONTROLLED INGESTION
    # ==================================================================
    print("[PHASE 1] CONTROLLED INGESTION")
    print("-" * 40)

    target_asins = []
    products = []
    total_snapshots = 0
    total_tokens_used = 0

    try:
        # --- Step 1: Discover ASINs ---
        with audit.time_phase("discovery"):
            if explicit_asins:
                target_asins = explicit_asins
                print(f"  Using {len(target_asins)} explicit ASINs (CLI)")
            elif skip_discovery:
                target_asins = pipeline._get_tracked_asins()
                print(f"  Using {len(target_asins)} tracked ASINs from DB")
            else:
                target_asins = pipeline.discover_category_asins()
                print(f"  Discovered {len(target_asins)} ASINs in category")

            audit.record_count("asins_discovered", len(target_asins))

        if not target_asins:
            print("  [WARN] No ASINs discovered — aborting")
            if pipeline_run_id:
                db.update_pipeline_run(pipeline_run_id, status="completed", asins_total=0)
            return 0

        # --- Step 2: Filter (optional) ---
        with audit.time_phase("filtering"):
            if not skip_filter and not skip_discovery:
                # First freshness check
                target_asins = pipeline.get_asins_needing_update(target_asins)
                print(f"  After freshness filter: {len(target_asins)} ASINs")

            # Apply max limit
            if len(target_asins) > max_asins:
                target_asins = target_asins[:max_asins]
                print(f"  Capped to {max_asins} ASINs")

            audit.record_count("asins_to_process", len(target_asins))

        if not target_asins:
            print("  [WARN] No ASINs need update — all fresh")
            if pipeline_run_id:
                db.update_pipeline_run(pipeline_run_id, status="completed", asins_total=0)
            return 0

        # --- Step 3: Fetch product data ---
        with audit.time_phase("fetch"):
            batch_size = min(100, len(target_asins))
            all_products = []

            for i in range(0, len(target_asins), batch_size):
                batch = target_asins[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(target_asins) + batch_size - 1) // batch_size

                print(f"  Fetching batch {batch_num}/{total_batches} ({len(batch)} ASINs)...")

                try:
                    batch_products = pipeline.fetch_product_batch(batch, include_history=True)
                    all_products.extend(batch_products)

                    stats = pipeline.keepa.get_stats()
                    total_tokens_used = stats.get("total_tokens_consumed", 0)
                    tokens_left = stats.get("tokens_remaining", 0)
                    print(f"    Got {len(batch_products)} products | tokens: {tokens_left} remaining")

                except KeepaAPIError as e:
                    for asin in batch:
                        audit.record_error(asin, "KeepaAPIError", str(e))
                    print(f"    [ERROR] Batch failed: {e}")

            products = all_products
            audit.record_count("products_fetched", len(products))
            print(f"  Total products fetched: {len(products)}")

        if not products:
            print("  [FAIL] No products fetched — aborting")
            if pipeline_run_id:
                db.update_pipeline_run(
                    pipeline_run_id,
                    status="failed",
                    error_message="No products fetched from Keepa",
                    asins_total=len(target_asins),
                    asins_failed=len(target_asins),
                )
            return 1

        # --- Step 4: Insert into DB (triggers generate events) ---
        with audit.time_phase("db_insert"):
            try:
                meta_count = pipeline.upsert_asin_metadata(products)
                print(f"  Upserted {meta_count} ASIN metadata records")

                total_snapshots = pipeline.insert_snapshots(products, session_id)
                print(f"  Inserted {total_snapshots} snapshots (triggers fired for events)")

                audit.record_count("metadata_upserted", meta_count)
                audit.record_count("snapshots_inserted", total_snapshots)

            except Exception as e:
                audit.record_error("db_insert", "DatabaseError", str(e))
                print(f"  [ERROR] DB insert failed: {e}")
                # Don't abort — we can still score

        # --- Step 5: Data Quality Gates ---
        with audit.time_phase("data_quality"):
            dq = {}
            total = len(products)
            price_missing = sum(1 for p in products if not p.current_snapshot.price_current)
            bsr_missing = sum(1 for p in products if not p.current_snapshot.bsr_primary)
            review_missing = sum(1 for p in products if not p.current_snapshot.review_count)

            dq["price_missing_pct"] = round(price_missing / total * 100, 1) if total else 0
            dq["bsr_missing_pct"] = round(bsr_missing / total * 100, 1) if total else 0
            dq["review_missing_pct"] = round(review_missing / total * 100, 1) if total else 0
            dq["total_products"] = total
            dq["has_history"] = sum(1 for p in products if p.has_price_history())
            dq["dq_passed"] = all(v < 30 for k, v in dq.items() if k.endswith("_pct"))

            audit.data_quality = dq

            print(f"  Data Quality Report:")
            print(f"    Products: {total}")
            print(f"    Price missing: {dq['price_missing_pct']}%")
            print(f"    BSR missing: {dq['bsr_missing_pct']}%")
            print(f"    Review missing: {dq['review_missing_pct']}%")
            print(f"    Has history: {dq['has_history']}/{total}")
            print(f"    DQ Gate: {'PASS' if dq['dq_passed'] else 'FAIL'}")

        # --- Step 6: Score all products (FREEZE MODE) ---
        with audit.time_phase("scoring"):
            scored = []
            for product in products:
                try:
                    # Build scorer inputs
                    product_data = product_to_scorer_input(product)
                    time_data = compute_time_signals(product)

                    # Update product_data with computed time signals for base scorer
                    product_data["stockout_count_90d"] = int(time_data["stockout_frequency"] * 3)
                    product_data["bsr_acceleration"] = time_data["bsr_acceleration"]

                    # Run economic scorer
                    result = scorer.score_economic(product_data, time_data)

                    scored.append({
                        "asin": product.asin,
                        "title": product.metadata.title[:60] if product.metadata.title else "N/A",
                        "final_score": result.final_score,
                        "base_score": round(result.base_score, 3),
                        "time_multiplier": round(result.time_multiplier, 2),
                        "window_days": result.window_days,
                        "urgency": result.window.value,
                        "monthly_profit": float(result.estimated_monthly_profit),
                        "annual_value": float(result.estimated_annual_value),
                        "risk_adjusted_value": float(result.risk_adjusted_value),
                        "rank_score": round(result.rank_score, 2),
                        "thesis": result.thesis,
                        "is_valid": result.final_score > 0,
                        "price": float(product.current_snapshot.price_current) if product.current_snapshot.price_current else None,
                        "bsr": product.current_snapshot.bsr_primary,
                        "reviews": product.current_snapshot.review_count,
                    })

                except Exception as e:
                    audit.record_error(product.asin, "ScoringError", str(e))

            audit.scoring_results = scored
            audit.record_count("products_scored", len(scored))

            # Sort by rank_score descending
            scored.sort(key=lambda x: x["rank_score"], reverse=True)

            print(f"  Scored {len(scored)} products")

        # --- Step 6b: Save opportunity artifacts to DB ---
        if scored and pipeline_run_id:
            try:
                pool = db.get_pool()
                conn = pool.getconn()
                try:
                    with conn.cursor() as cur:
                        inserted = 0
                        for rank, opp in enumerate(scored, 1):
                            if not opp.get("is_valid", True):
                                continue
                            cur.execute("""
                                INSERT INTO opportunity_artifacts (
                                    artifact_id, run_id, asin, rank,
                                    final_score, base_score, time_multiplier,
                                    component_scores, time_pressure_factors,
                                    thesis, action_recommendation,
                                    estimated_monthly_profit, estimated_annual_value,
                                    risk_adjusted_value, window_days, urgency_level,
                                    economic_events, input_data,
                                    amazon_price, review_count, rating, bsr_primary
                                ) VALUES (
                                    gen_random_uuid(), %s, %s, %s,
                                    %s, %s, %s,
                                    %s, %s,
                                    %s, %s,
                                    %s, %s,
                                    %s, %s, %s,
                                    %s, %s,
                                    %s, %s, %s, %s
                                )
                                ON CONFLICT DO NOTHING
                            """, (
                                pipeline_run_id, opp["asin"], rank,
                                opp["final_score"], opp["base_score"], opp["time_multiplier"],
                                json.dumps({}), json.dumps({}),
                                opp.get("thesis", ""), _generate_action(opp.get("window_days", 90)),
                                opp["monthly_profit"], opp["annual_value"],
                                opp["risk_adjusted_value"], opp["window_days"], opp.get("urgency", "standard"),
                                json.dumps([]), json.dumps({"title": opp.get("title", "")}),
                                opp.get("price"), opp.get("reviews"), None, opp.get("bsr"),
                            ))
                            inserted += 1
                        conn.commit()
                    print(f"  Saved {inserted} opportunity artifacts to DB")
                finally:
                    pool.putconn(conn)
            except Exception as e:
                audit.warn(f"Failed to save artifacts: {e}")

        # --- Step 6c: Review Intelligence (deterministic, skip if no reviews) ---
        with audit.time_phase("review_intelligence"):
            try:
                from src.reviews import ReviewSignalExtractor, ReviewInsightAggregator
                extractor = ReviewSignalExtractor()
                aggregator = ReviewInsightAggregator()

                pool = db.get_pool()
                conn = pool.getconn()
                try:
                    # Check if reviews table has data for scored ASINs
                    scored_asins = [opp["asin"] for opp in scored if opp.get("is_valid", True)]
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM reviews WHERE asin = ANY(%s)",
                            (scored_asins,)
                        )
                        review_count = cur.fetchone()[0]

                    if review_count == 0:
                        print(f"  Review Intelligence: SKIP (0 reviews in DB for {len(scored_asins)} ASINs)")
                        audit.record_count("reviews_analyzed", 0)
                    else:
                        analyzed = 0
                        for asin in scored_asins:
                            reviews_data = aggregator.load_reviews_from_db(conn, asin)
                            if not reviews_data:
                                continue

                            defects = extractor.extract_defects(reviews_data)
                            wishes = extractor.extract_wish_patterns(reviews_data)
                            negative_count = sum(1 for r in reviews_data if r.get("rating", 5) <= 3)

                            profile = aggregator.build_profile(
                                asin=asin,
                                defects=defects,
                                wishes=wishes,
                                reviews_analyzed=len(reviews_data),
                                negative_reviews_analyzed=negative_count,
                            )

                            if profile.reviews_ready:
                                aggregator.save_profile(conn, profile, pipeline_run_id)
                                analyzed += 1

                        print(f"  Review Intelligence: {analyzed} ASINs profiled ({review_count} reviews)")
                        audit.record_count("reviews_analyzed", review_count)
                        audit.record_count("review_profiles_created", analyzed)
                finally:
                    pool.putconn(conn)
            except ImportError:
                print(f"  Review Intelligence: SKIP (module not available)")
            except Exception as e:
                audit.warn(f"Review intelligence failed (non-blocking): {e}")

        # --- Step 6e: Economic Event Detection (V2.0) ---
        with audit.time_phase("event_detection"):
            try:
                from src.events.economic_events import EconomicEventDetector

                detector = EconomicEventDetector()
                pool = db.get_pool()
                conn = pool.getconn()
                try:
                    events_detected = 0
                    events_inserted = 0

                    for product in products:
                        asin = product.asin
                        snap = product.current_snapshot

                        # Build metrics dict for detector
                        time_signals = compute_time_signals(product)

                        # Get review data if available (from review_improvement_profiles)
                        negative_pct = 0.10  # Default
                        wish_mentions = 0
                        common_complaints = []
                        rating_now = float(snap.rating_average) if snap.rating_average else 4.0
                        rating_30d_ago = rating_now  # No historical data yet

                        try:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    SELECT top_defects, missing_features, improvement_score
                                    FROM review_improvement_profiles
                                    WHERE asin = %s
                                    ORDER BY computed_at DESC LIMIT 1
                                """, (asin,))
                                prof = cur.fetchone()
                                if prof:
                                    defects_raw = prof[0] if isinstance(prof[0], list) else json.loads(prof[0] or "[]")
                                    features_raw = prof[1] if isinstance(prof[1], list) else json.loads(prof[1] or "[]")
                                    negative_pct = min(0.5, len(defects_raw) * 0.05 + 0.05) if defects_raw else 0.10
                                    wish_mentions = sum(f.get("mentions", 0) for f in features_raw)
                                    common_complaints = [d.get("type", "") for d in defects_raw[:5]]
                        except Exception:
                            pass  # Use defaults

                        metrics = {
                            # Supply shock signals
                            "stockouts_90d": int(time_signals.get("stockout_frequency", 0) * 3),
                            "bsr_change_30d": -time_signals.get("bsr_acceleration", 0),  # Invert (acceleration = improvement)
                            "price_change_30d": 0.0,  # Would need history comparison
                            "competitors_stockout": 0,  # Not available from Keepa

                            # Competitor collapse signals
                            "seller_churn_90d": time_signals.get("seller_churn_90d", 0),
                            "top_seller_gone": False,  # Would need historical seller data
                            "buybox_rotation_change": 0.0,  # Not available
                            "new_entrants": 0,  # Not available

                            # Quality decay signals
                            "negative_review_pct": negative_pct,
                            "negative_review_trend": 0.0,  # Would need historical review data
                            "wish_mentions": wish_mentions,
                            "common_complaints": common_complaints,
                            "rating_30d_ago": rating_30d_ago,
                            "rating_now": rating_now,
                        }

                        # Detect events
                        detected = detector.detect_all_events(asin, metrics)
                        events_detected += len(detected)

                        # Insert into economic_events table (with fingerprint dedup)
                        for event in detected:
                            # Generate fingerprint from signals
                            signals_json = json.dumps(event.supporting_signals, sort_keys=True)
                            fingerprint = hashlib.sha256(signals_json.encode()).hexdigest()[:16]

                            try:
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        INSERT INTO economic_events (
                                            asin, event_type, event_subtype, confidence, urgency,
                                            thesis, signals, event_fingerprint, run_id
                                        ) VALUES (%s, %s, %s, %s, %s::event_urgency, %s, %s, %s, %s)
                                        ON CONFLICT (asin, event_type, event_fingerprint) DO NOTHING
                                    """, (
                                        asin,
                                        event.event_type.value.upper(),
                                        getattr(event, 'event_subtype', None),
                                        event.signal_strength,  # Use signal_strength as confidence 0-1
                                        event.urgency.value.upper(),
                                        event.thesis,
                                        json.dumps(event.supporting_signals),
                                        fingerprint,
                                        pipeline_run_id,
                                    ))
                                    if cur.rowcount > 0:
                                        events_inserted += 1
                            except Exception as e:
                                logger.debug(f"Event insert skipped for {asin}: {e}")

                    conn.commit()
                    print(f"  Event Detection: {events_detected} detected, {events_inserted} new inserted")
                    audit.record_count("events_detected", events_detected)
                    audit.record_count("events_inserted", events_inserted)
                finally:
                    pool.putconn(conn)
            except ImportError as e:
                print(f"  Event Detection: SKIP (module not available: {e})")
            except Exception as e:
                audit.warn(f"Event detection failed (non-blocking): {e}")

        # --- Step 6d: Spec Generation (conditional) ---
        with audit.time_phase("spec_generation"):
            try:
                from src.specs import SpecGenerator

                spec_gen = SpecGenerator()
                pool = db.get_pool()
                conn = pool.getconn()
                try:
                    specs_generated = 0
                    specs_skipped = 0
                    for opp in scored:
                        if not opp.get("is_valid", True):
                            continue
                        asin = opp["asin"]

                        # Activation rule: score >= 60, reviews >= 20, has profile with dominant_pain
                        if opp["final_score"] < 60:
                            specs_skipped += 1
                            continue

                        # Load profile for this ASIN
                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT top_defects, missing_features, dominant_pain,
                                       improvement_score, reviews_analyzed, negative_reviews_analyzed,
                                       reviews_ready
                                FROM review_improvement_profiles
                                WHERE asin = %s
                                ORDER BY computed_at DESC LIMIT 1
                            """, (asin,))
                            prof_row = cur.fetchone()

                        if not prof_row:
                            specs_skipped += 1
                            continue

                        reviews_analyzed = prof_row[4] or 0
                        dominant_pain = prof_row[2]
                        if reviews_analyzed < 20 or not dominant_pain:
                            specs_skipped += 1
                            continue

                        # Build profile object
                        from src.reviews.review_models import (
                            DefectSignal, FeatureRequest, ProductImprovementProfile,
                        )

                        top_defects_raw = prof_row[0] if isinstance(prof_row[0], list) else json.loads(prof_row[0] or "[]")
                        features_raw = prof_row[1] if isinstance(prof_row[1], list) else json.loads(prof_row[1] or "[]")

                        defects = [
                            DefectSignal(
                                defect_type=d["type"], frequency=d.get("freq", 0),
                                severity_score=d.get("severity", 0.0),
                                example_quotes=[], total_reviews_scanned=reviews_analyzed,
                                negative_reviews_scanned=prof_row[5] or 0,
                            )
                            for d in top_defects_raw
                        ]
                        features = [
                            FeatureRequest(
                                feature=f["feature"], mentions=f.get("mentions", 0),
                                confidence=f.get("confidence", 0.0),
                                wish_strength=f.get("mentions", 0) * 1.5,
                            )
                            for f in features_raw
                        ]

                        profile = ProductImprovementProfile(
                            asin=asin, top_defects=defects, missing_features=features,
                            dominant_pain=dominant_pain,
                            improvement_score=float(prof_row[3]),
                            reviews_analyzed=reviews_analyzed,
                            negative_reviews_analyzed=prof_row[5] or 0,
                            reviews_ready=prof_row[6] or False,
                        )

                        bundle = spec_gen.generate(profile)
                        spec_gen.save_bundle(conn, bundle, run_id=pipeline_run_id)
                        specs_generated += 1

                    print(f"  Spec Generation: {specs_generated} bundles generated, {specs_skipped} skipped")
                    audit.record_count("specs_generated", specs_generated)
                    audit.record_count("specs_skipped", specs_skipped)
                finally:
                    pool.putconn(conn)
            except ImportError:
                print(f"  Spec Generation: SKIP (module not available)")
            except Exception as e:
                audit.warn(f"Spec generation failed (non-blocking): {e}")

        # --- Step 6f: Auto-thesis generation (V2.0) ---
        with audit.time_phase("thesis_generation"):
            try:
                # Config from env
                max_theses = int(os.getenv("MAX_THESES_PER_RUN", "20"))
                cache_days = int(os.getenv("THESIS_CACHE_DAYS", "7"))

                pool = db.get_pool()
                conn = pool.getconn()
                try:
                    theses_generated = 0
                    theses_cached = 0

                    # Get top opportunities by score (>= 50)
                    eligible = [opp for opp in scored if opp.get("final_score", 0) >= 50 and opp.get("is_valid", True)]
                    eligible = eligible[:max_theses]

                    for opp in eligible:
                        asin = opp["asin"]

                        # Check cache: skip if recent thesis exists
                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT 1 FROM opportunity_theses
                                WHERE asin = %s AND generated_at > NOW() - INTERVAL '%s days'
                                LIMIT 1
                            """, (asin, cache_days))
                            if cur.fetchone():
                                theses_cached += 1
                                continue

                        # Generate thesis
                        headline = f"Score {opp['final_score']} | {opp.get('urgency', 'standard').upper()} | {opp['window_days']}j"
                        thesis = opp.get("thesis", "")

                        # Build economic estimates JSON
                        economic_estimates = {
                            "monthly_profit": opp.get("monthly_profit", 0),
                            "annual_value": opp.get("annual_value", 0),
                            "risk_adjusted_value": opp.get("risk_adjusted_value", 0),
                            "amazon_price": opp.get("price"),
                            "base_score": opp.get("base_score", 0),
                            "time_multiplier": opp.get("time_multiplier", 1.0),
                        }

                        # Get associated events
                        source_events = []
                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT event_type, thesis, urgency
                                FROM economic_events
                                WHERE asin = %s AND detected_at > NOW() - INTERVAL '7 days'
                            """, (asin,))
                            for ev_row in cur.fetchall():
                                source_events.append({
                                    "event_type": ev_row[0],
                                    "thesis": ev_row[1],
                                    "urgency": ev_row[2],
                                })

                        # Save thesis
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO opportunity_theses (
                                    asin, run_id, headline, thesis, confidence,
                                    action_recommendation, urgency, economic_estimates,
                                    source_events
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (asin, run_id) DO NOTHING
                            """, (
                                asin, pipeline_run_id, headline, thesis,
                                opp.get("base_score", 0.5),
                                _generate_action(opp["window_days"]),
                                opp.get("urgency", "standard").upper(),
                                json.dumps(economic_estimates),
                                json.dumps(source_events),
                            ))
                            if cur.rowcount > 0:
                                theses_generated += 1

                    conn.commit()
                    print(f"  Thesis Generation: {theses_generated} generated, {theses_cached} cached (skip)")
                    audit.record_count("theses_generated", theses_generated)
                    audit.record_count("theses_cached", theses_cached)
                finally:
                    pool.putconn(conn)
            except Exception as e:
                audit.warn(f"Thesis generation failed (non-blocking): {e}")

        # --- Step 6g: Slack Notifications (V2.0) ---
        with audit.time_phase("notifications"):
            try:
                from src.notifications import SlackNotifier
                notifier = SlackNotifier()

                if not notifier.is_configured():
                    print(f"  Notifications: SKIP (not configured)")
                else:
                    # Determine "new" opportunities to notify
                    # Criteria: score >= 50 AND (new ASIN OR critical event OR score +10)
                    to_notify = []

                    pool = db.get_pool()
                    conn = pool.getconn()
                    try:
                        for opp in scored[:20]:  # Top 20 max
                            if opp.get("final_score", 0) < 50 or not opp.get("is_valid", True):
                                continue

                            asin = opp["asin"]
                            reasons = []

                            # Check if new ASIN (first seen)
                            with conn.cursor() as cur:
                                cur.execute("""
                                    SELECT COUNT(*) FROM opportunity_artifacts
                                    WHERE asin = %s AND run_id != %s
                                """, (asin, pipeline_run_id))
                                prev_count = cur.fetchone()[0]
                                if prev_count == 0:
                                    reasons.append("Nouvel ASIN")

                            # Check for critical/high event
                            with conn.cursor() as cur:
                                cur.execute("""
                                    SELECT event_type, urgency FROM economic_events
                                    WHERE asin = %s AND detected_at > NOW() - INTERVAL '24 hours'
                                      AND urgency IN ('CRITICAL', 'HIGH')
                                    LIMIT 1
                                """, (asin,))
                                ev = cur.fetchone()
                                if ev:
                                    reasons.append(f"Event {ev[1]}: {ev[0]}")

                            # Check score increase (>= +10)
                            with conn.cursor() as cur:
                                cur.execute("""
                                    SELECT final_score FROM opportunity_artifacts
                                    WHERE asin = %s AND run_id != %s
                                    ORDER BY scored_at DESC LIMIT 1
                                """, (asin, pipeline_run_id))
                                prev_row = cur.fetchone()
                                if prev_row:
                                    prev_score = prev_row[0] or 0
                                    if opp["final_score"] - prev_score >= 10:
                                        reasons.append(f"Score +{opp['final_score'] - prev_score}")

                            if reasons:
                                to_notify.append({
                                    "asin": asin,
                                    "title": opp.get("title", "")[:40],
                                    "final_score": opp["final_score"],
                                    "window_days": opp["window_days"],
                                    "annual_value": opp.get("annual_value", 0),
                                    "urgency": opp.get("urgency", "standard").upper(),
                                    "reason": " | ".join(reasons),
                                })
                    finally:
                        pool.putconn(conn)

                    if to_notify:
                        success = notifier.notify_new_opportunities(
                            opportunities=to_notify,
                            run_id=pipeline_run_id,
                        )
                        print(f"  Notifications: {len(to_notify)} opportunities {'sent' if success else 'FAILED'}")
                        audit.record_count("notifications_sent", len(to_notify) if success else 0)
                    else:
                        print(f"  Notifications: No new opportunities to notify")
                        audit.record_count("notifications_sent", 0)

            except ImportError:
                print(f"  Notifications: SKIP (module not available)")
            except Exception as e:
                audit.warn(f"Notifications failed (non-blocking): {e}")

        # --- Step 7: Refresh materialized views ---
        with audit.time_phase("refresh_views"):
            try:
                pipeline.refresh_materialized_views()
                print(f"  Materialized views refreshed")
            except Exception as e:
                audit.warn(f"Mat view refresh failed: {e}")

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        audit.record_error("pipeline", "UnexpectedError", str(e))
        if pipeline_run_id:
            db.update_pipeline_run(pipeline_run_id, status="failed", error_message=str(e))
        raise
    finally:
        pipeline.close()

    # ==================================================================
    # PHASE 1b: RESULTS & AUDIT
    # ==================================================================
    total_elapsed = time.monotonic() - start_time
    audit.timings["total"] = total_elapsed

    # Update pipeline_run in DB
    error_rate = len(audit.errors) / max(len(target_asins), 1)
    final_status = "completed" if error_rate < 0.15 else "degraded"

    if pipeline_run_id:
        try:
            db.update_pipeline_run(
                pipeline_run_id,
                status=final_status,
                asins_total=len(target_asins),
                asins_ok=len(products) - len([e for e in audit.errors if e["type"] != "ScoringError"]),
                asins_failed=len(audit.errors),
                duration_ingestion_ms=int(audit.timings.get("fetch", 0) * 1000),
                duration_events_ms=int(audit.timings.get("db_insert", 0) * 1000),
                duration_scoring_ms=int(audit.timings.get("scoring", 0) * 1000),
                duration_refresh_ms=int(audit.timings.get("refresh_views", 0) * 1000),
                duration_total_ms=int(total_elapsed * 1000),
                opportunities_generated=len([s for s in scored if s["final_score"] >= 40]),
                events_generated=total_snapshots,  # events auto-generated by triggers
                keepa_tokens_used=total_tokens_used,
                error_rate=round(error_rate, 4),
                error_budget_breached=(error_rate >= 0.15),
                shortlist_frozen=True,  # FREEZE MODE
                dq_price_missing_pct=audit.data_quality.get("price_missing_pct", 0),
                dq_bsr_missing_pct=audit.data_quality.get("bsr_missing_pct", 0),
                dq_review_missing_pct=audit.data_quality.get("review_missing_pct", 0),
                dq_passed=audit.data_quality.get("dq_passed", False),
            )
        except Exception as e:
            audit.warn(f"Failed to update pipeline_run: {e}")

    # ==================================================================
    # PRINT RESULTS
    # ==================================================================
    print()
    print("=" * 70)
    print("  RESULTS — CONTROLLED RUN")
    print("=" * 70)
    print()

    # Top 10 opportunities
    top10 = scored[:10]
    if top10:
        print("  TOP 10 OPPORTUNITIES (FROZEN — observation only)")
        print("  " + "-" * 66)
        print(f"  {'#':>2}  {'Score':>5}  {'Window':>6}  {'Annual$':>8}  {'BSR':>7}  {'Price':>6}  ASIN / Title")
        print("  " + "-" * 66)
        for i, opp in enumerate(top10, 1):
            price_str = f"${opp['price']:.0f}" if opp['price'] else "N/A"
            bsr_str = f"{opp['bsr']:,}" if opp['bsr'] else "N/A"
            annual_str = f"${opp['annual_value']:,.0f}"
            title = opp['title'][:35] if opp['title'] else "N/A"
            print(f"  {i:>2}  {opp['final_score']:>5}  {opp['window_days']:>4}j  {annual_str:>8}  {bsr_str:>7}  {price_str:>6}  {opp['asin']} {title}")
        print()

    # Score distribution
    dist = audit._scoring_distribution()
    print("  SCORE DISTRIBUTION")
    print("  " + "-" * 40)
    for bucket, count in dist.items():
        bar = "#" * count
        print(f"  {bucket:>8}: {count:>3}  {bar}")
    print()

    # Summary stats
    print("  SUMMARY")
    print("  " + "-" * 40)
    print(f"  Run ID:              {run_id}")
    print(f"  Pipeline Run:        {pipeline_run_id[:8] if pipeline_run_id else 'N/A'}...")
    print(f"  Status:              {final_status.upper()}")
    print(f"  ASINs discovered:    {audit.counts.get('asins_discovered', 0):,}")
    print(f"  ASINs processed:     {audit.counts.get('asins_to_process', 0):,}")
    print(f"  Products fetched:    {audit.counts.get('products_fetched', 0):,}")
    print(f"  Snapshots inserted:  {audit.counts.get('snapshots_inserted', 0):,}")
    print(f"  Products scored:     {audit.counts.get('products_scored', 0):,}")
    print(f"  Errors:              {len(audit.errors)}")
    print(f"  Error rate:          {error_rate*100:.1f}%")
    print(f"  Tokens used:         {total_tokens_used:,}")
    print(f"  Total duration:      {total_elapsed:.1f}s")
    print(f"  DQ passed:           {'YES' if audit.data_quality.get('dq_passed') else 'NO'}")
    print(f"  Shortlist frozen:    YES (observation mode)")
    print()

    # Timing breakdown
    print("  TIMING BREAKDOWN")
    print("  " + "-" * 40)
    for phase, elapsed_s in audit.timings.items():
        if phase != "total":
            pct = (elapsed_s / total_elapsed * 100) if total_elapsed > 0 else 0
            print(f"  {phase:>20}: {elapsed_s:>6.1f}s ({pct:>4.1f}%)")
    print(f"  {'TOTAL':>20}: {total_elapsed:>6.1f}s")
    print()

    # Data quality
    print("  DATA QUALITY")
    print("  " + "-" * 40)
    for k, v in audit.data_quality.items():
        print(f"  {k:>25}: {v}")
    print()

    # Save audit to file
    audit_file = project_root / "data" / f"audit_run_{run_id}.json"
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_file, "w") as f:
        json.dump(audit.summary(), f, indent=2, default=str)
    print(f"  Audit saved to: {audit_file}")
    print()

    # Save top opportunities to file
    if scored:
        opp_file = project_root / "data" / f"opportunities_run_{run_id}.json"
        with open(opp_file, "w") as f:
            json.dump(scored, f, indent=2, default=str)
        print(f"  Opportunities saved to: {opp_file}")
        print()

    # Warnings
    if audit.warnings:
        print("  WARNINGS")
        print("  " + "-" * 40)
        for w in audit.warnings:
            print(f"  [!] {w}")
        print()

    print("=" * 70)
    print(f"  Controlled Run {run_id} — {final_status.upper()}")
    print(f"  FREEZE MODE: No shortlist changes. Review results above.")
    print(f"  Next step: Run 2 in 24-48h for stability check.")
    print("=" * 70)
    print()

    return 0 if final_status == "completed" else 1


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Smartacus Controlled Pipeline Runner (Run 1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--max-asins", type=int, default=100, help="Max ASINs to process (default: 100)")
    parser.add_argument("--skip-discovery", action="store_true", help="Use existing DB ASINs instead of Keepa discovery")
    parser.add_argument("--skip-filter", action="store_true", help="Skip criteria filtering")
    parser.add_argument("--asins", type=str, default=None, help="Comma-separated ASINs to use (skips discovery)")
    parser.add_argument("--freeze", action="store_true", default=True, help="Freeze mode: score but don't promote to shortlist (default: True)")
    parser.add_argument("--no-freeze", action="store_true", help="Disable freeze mode: promote scored items to shortlist")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    parser.add_argument("--log-file", type=str, default=None, help="Log to file")

    args = parser.parse_args()

    setup_logging(verbose=args.verbose, log_file=args.log_file)

    explicit_asins = None
    if args.asins:
        explicit_asins = [a.strip() for a in args.asins.split(",") if a.strip()]

    return run_controlled(
        max_asins=args.max_asins,
        skip_discovery=args.skip_discovery,
        skip_filter=args.skip_filter,
        verbose=args.verbose,
        explicit_asins=explicit_asins,
    )


if __name__ == "__main__":
    sys.exit(main())
