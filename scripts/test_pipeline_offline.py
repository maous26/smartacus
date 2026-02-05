#!/usr/bin/env python3
"""
Offline pipeline validation: mock ProductData → DB insert → triggers → scoring.
No Keepa API calls. Tests the full chain with realistic data.
"""
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.data.data_models import (
    ProductData, ProductSnapshot, ProductMetadata,
    PriceHistory, BSRHistory, StockStatus, FulfillmentType,
)
from src.data.ingestion_pipeline import IngestionPipeline
from src.scoring import EconomicScorer

# Import db directly to avoid FastAPI
import importlib.util
db_spec = importlib.util.spec_from_file_location("db", project_root / "src" / "api" / "db.py")
db = importlib.util.module_from_spec(db_spec)
db_spec.loader.exec_module(db)


def make_mock_product(asin: str, title: str, price: float, bsr: int, reviews: int, rating: float) -> ProductData:
    """Create a realistic mock ProductData."""
    now = datetime.utcnow()

    # Generate 30 days of price history
    price_history = []
    for i in range(30):
        ts = now - timedelta(days=30 - i)
        variation = price * (1 + (i % 5 - 2) * 0.02)  # +/- 4% variation
        price_history.append(PriceHistory(timestamp=ts, price_cents=int(variation * 100)))

    # Generate 30 days of BSR history
    bsr_history = []
    for i in range(30):
        ts = now - timedelta(days=30 - i)
        bsr_variation = int(bsr * (1 + (i % 7 - 3) * 0.05))  # +/- 15% variation
        bsr_history.append(BSRHistory(timestamp=ts, bsr=max(1, bsr_variation)))

    snapshot = ProductSnapshot(
        asin=asin,
        captured_at=now,
        price_current=Decimal(str(price)),
        price_original=Decimal(str(price * 1.2)),
        bsr_primary=bsr,
        bsr_category_name="Cell Phone Automobile Cradles",
        stock_status=StockStatus.IN_STOCK,
        fulfillment=FulfillmentType.FBA,
        seller_count=8,
        rating_average=Decimal(str(rating)),
        rating_count=reviews,
        review_count=reviews,
        data_source="mock_test",
    )

    metadata = ProductMetadata(
        asin=asin,
        title=title,
        brand="TestBrand",
        category_id=7072562011,
        category_path=["Cell Phones & Accessories", "Accessories", "Car Mounts"],
    )

    return ProductData(
        asin=asin,
        metadata=metadata,
        current_snapshot=snapshot,
        price_history=price_history,
        bsr_history=bsr_history,
    )


def main():
    print("=" * 60)
    print("  OFFLINE PIPELINE VALIDATION")
    print("=" * 60)
    print()

    # Create 3 realistic mock products
    products = [
        make_mock_product("MOCK00001A", "Premium Magnetic Car Phone Mount", 24.99, 3500, 2800, 4.5),
        make_mock_product("MOCK00002B", "Universal Dashboard Phone Holder", 15.99, 12000, 850, 4.2),
        make_mock_product("MOCK00003C", "Wireless Charging Car Mount Pro", 39.99, 1200, 5200, 4.7),
    ]

    # Step 1: DB Insert
    print("[1] DB INSERT (metadata + snapshots)")
    print("-" * 40)
    pipeline = IngestionPipeline()
    session_id = str(uuid.uuid4())

    try:
        meta_count = pipeline.upsert_asin_metadata(products)
        print(f"  Metadata upserted: {meta_count}")

        snap_count = pipeline.insert_snapshots(products, session_id)
        print(f"  Snapshots inserted: {snap_count}")
        print(f"  (Triggers should have fired for price/bsr/stock events)")
    except Exception as e:
        print(f"  [ERROR] DB insert failed: {e}")
        pipeline.close()
        return 1

    # Step 2: Verify events were created by triggers
    print()
    print("[2] VERIFY TRIGGER EVENTS")
    print("-" * 40)
    try:
        pool = db.get_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                for table in ["price_events", "bsr_events", "stock_events"]:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE asin LIKE 'MOCK%'")
                    count = cur.fetchone()[0]
                    print(f"  {table}: {count} events")

                # Show sample events
                cur.execute("""
                    SELECT asin, price_new, price_old, change_pct
                    FROM price_events WHERE asin LIKE 'MOCK%'
                    ORDER BY detected_at DESC LIMIT 3
                """)
                rows = cur.fetchall()
                if rows:
                    print(f"  Sample price events:")
                    for r in rows:
                        print(f"    {r[0]}: ${r[1]} (was ${r[2]}, {r[3]}% change)")
        finally:
            pool.putconn(conn)
    except Exception as e:
        print(f"  [WARN] Event verification failed: {e}")

    # Step 3: Scoring
    print()
    print("[3] SCORING (Economic Scorer)")
    print("-" * 40)
    scorer = EconomicScorer()

    # Import helpers from run_controlled
    sys.path.insert(0, str(project_root / "scripts"))
    from run_controlled import product_to_scorer_input, compute_time_signals

    for product in products:
        try:
            product_data = product_to_scorer_input(product)
            time_data = compute_time_signals(product)
            product_data["stockout_count_90d"] = int(time_data["stockout_frequency"] * 3)
            product_data["bsr_acceleration"] = time_data["bsr_acceleration"]

            result = scorer.score_economic(product_data, time_data)

            print(f"  {product.asin} ({product.metadata.title[:40]})")
            print(f"    Score: {result.final_score} | Base: {result.base_score:.3f} | TimeMult: {result.time_multiplier:.2f}")
            print(f"    Window: {result.window_days}d ({result.window.value}) | Monthly profit: ${result.estimated_monthly_profit:.0f}")
            print(f"    Thesis: {result.thesis[:80]}")
            print()
        except Exception as e:
            print(f"  [ERROR] {product.asin}: {e}")

    # Step 4: Refresh mat views
    print("[4] REFRESH MATERIALIZED VIEWS")
    print("-" * 40)
    try:
        pipeline.refresh_materialized_views()
        print("  Views refreshed OK")
    except Exception as e:
        print(f"  [WARN] Refresh failed: {e}")

    # Step 5: Verify data in mat views
    print()
    print("[5] VERIFY MATERIALIZED VIEWS")
    print("-" * 40)
    try:
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_latest_snapshots WHERE asin LIKE 'MOCK%'")
                count = cur.fetchone()[0]
                print(f"  mv_latest_snapshots: {count} mock records")

                cur.execute("SELECT COUNT(*) FROM mv_asin_stats_7d WHERE asin LIKE 'MOCK%'")
                count = cur.fetchone()[0]
                print(f"  mv_asin_stats_7d: {count} mock records")
        finally:
            pool.putconn(conn)
    except Exception as e:
        print(f"  [WARN] Mat view check failed: {e}")

    # Cleanup mock data
    print()
    print("[6] CLEANUP MOCK DATA")
    print("-" * 40)
    try:
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                for table in ["price_events", "bsr_events", "stock_events", "asin_snapshots", "asins"]:
                    cur.execute(f"DELETE FROM {table} WHERE asin LIKE 'MOCK%'")
                    print(f"  Cleaned {table}: {cur.rowcount} rows")
                conn.commit()
        finally:
            pool.putconn(conn)
    except Exception as e:
        print(f"  [WARN] Cleanup failed: {e}")

    pipeline.close()

    print()
    print("=" * 60)
    print("  OFFLINE VALIDATION COMPLETE")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
