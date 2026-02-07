# SMARTACUS — Document d'Architecture Complet

> **Version** : 1.1
> **Date** : 5 février 2026
> **Statut** : Run 1 validé (100 ASINs, 0 erreurs, DQ PASS)

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture système](#2-architecture-système)
3. [Stack technique](#3-stack-technique)
4. [Structure du projet](#4-structure-du-projet)
5. [Couche Données (src/data)](#5-couche-données-srcdata)
6. [Moteur de Scoring (src/scoring)](#6-moteur-de-scoring-srcscoring)
7. [API REST (src/api)](#7-api-rest-srcapi)
8. [Frontend (web/)](#8-frontend-web)
9. [Base de données](#9-base-de-données)
10. [Pipeline d'ingestion](#10-pipeline-dingestion)
11. [Détection d'événements](#11-détection-dévénements)
12. [IA et Agents](#12-ia-et-agents)
13. [RAG (Retrieval-Augmented Generation)](#13-rag-retrieval-augmented-generation)
14. [Orchestration & Monitoring](#14-orchestration--monitoring)
15. [Flux de données complet](#15-flux-de-données-complet)
16. [Sécurité & Configuration](#16-sécurité--configuration)
17. [Performance & Optimisations](#17-performance--optimisations)
18. [Décisions architecturales](#18-décisions-architecturales)
19. [Résultats Run 1](#19-résultats-run-1)
20. [Roadmap](#20-roadmap)

---

## 1. Vue d'ensemble

**Smartacus** est une sonde économique Amazon qui détecte automatiquement les opportunités de marché dans la niche *Car Phone Mounts*. Le système collecte des données produit via l'API Keepa, calcule un score d'opportunité déterministe, et présente les résultats via une interface web interactive.

### Proposition de valeur

```
Données Keepa → Scoring déterministe → Classement par valeur × urgence → Décision utilisateur
```

### Principes fondamentaux

| Principe | Implémentation |
|----------|---------------|
| **100% déterministe** | Scoring sans ML, entièrement explicable |
| **Le temps est un multiplicateur** | Score × TimeMultiplier, pas un simple composant additif |
| **Audit trail complet** | Chaque run enregistré avec métriques, timing, erreurs |
| **Freeze mode** | Scoring sans promotion en shortlist (observation) |
| **Fallback gracieux avec garde-fous** | Données mock si API/DB indisponibles, mais actions (sourcing, export, IA) **désactivées** en mode DEMO. Bannière + watermark explicites |
| **Décisionnel côté backend** | Les utilisateurs ne voient que les articles proposés |

---

## 2. Architecture système

```
┌─────────────────────────────────────────────────────────────────┐
│                         UTILISATEUR                              │
│                    http://localhost:3000                          │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js 14)                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Dashboard │  │ Detail Panel │  │ Filters  │  │ Agent Chat │  │
│  └──────────┘  └──────────────┘  └──────────┘  └────────────┘  │
│                    Proxy /api/* → :8000                          │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI + Uvicorn)                    │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │ ShortlistSvc │  │ PipelineSvc    │  │ AI Agents          │   │
│  │ (DB → API)   │  │ (Run tracking) │  │ (Claude/OpenAI)    │   │
│  └──────┬───────┘  └───────┬────────┘  └────────────────────┘   │
│         │                  │                                     │
│  ┌──────┴──────────────────┴─────────────────────────────────┐  │
│  │                  DB Connection Pool                        │  │
│  │              (psycopg2 ThreadedPool)                       │  │
│  └──────────────────────────┬────────────────────────────────┘  │
└─────────────────────────────┼────────────────────────────────────┘
                              │ PostgreSQL Wire Protocol (SSL)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              RAILWAY POSTGRESQL 17.7                              │
│  ┌────────┐ ┌──────────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ asins  │ │asin_snapshots│ │ *_events  │ │opportunity_      │ │
│  │ (108)  │ │    (108)     │ │ (triggers)│ │artifacts (100)   │ │
│  └────────┘ └──────────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────────┐  ┌──────────┐  ┌───────────────────────────┐ │
│  │pipeline_runs │  │ mat views│  │  4 triggers auto-events   │ │
│  │    (13)      │  │   (4)    │  │  3 views, 92+ indexes     │ │
│  └──────────────┘  └──────────┘  └───────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Batch Ingestion (scripts/)
┌─────────────────────────────┼────────────────────────────────────┐
│              PIPELINE CLI (run_controlled.py)                     │
│  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌───────┐  ┌───────┐ │
│  │ Discovery│→ │  Fetch   │→ │DB Insert│→ │ Score │→ │ Audit │ │
│  │ (Keepa)  │  │ (Keepa)  │  │(triggers│  │(econ) │  │(JSON) │ │
│  └──────────┘  └──────────┘  │ fire)   │  └───────┘  └───────┘ │
│                              └────────┘                          │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       KEEPA API                                  │
│           21 tokens/min | Discovery + Product queries            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Stack technique

| Couche | Technologies | Version |
|--------|-------------|---------|
| **Frontend** | Next.js, React, TypeScript, Tailwind CSS | 14.2, 18.3 |
| **Backend API** | FastAPI, Uvicorn, Pydantic | 0.109+ |
| **Scoring** | Python pur (pas de ML) | 3.12 |
| **Data** | Keepa API, psycopg2, NumPy, Pandas | keepa 1.4.3 |
| **Database** | PostgreSQL (Railway) | 17.7 |
| **Extensions DB** | pg_trgm, btree_gin | natif |
| **LLM** | Anthropic Claude, OpenAI | claude-3-opus |
| **CLI** | argparse, tqdm, rich | stdlib |
| **Tests** | pytest, pytest-cov | 7.4+ |

### Dépendances principales (requirements.txt)

```
# Core
keepa>=1.3.0
psycopg2-binary>=2.9.9
python-dotenv>=1.0.0
pydantic>=2.5.0
numpy>=1.24.0

# Web
fastapi>=0.109.0
uvicorn[standard]>=0.27.0

# LLM
anthropic>=0.40.0
openai>=1.50.0

# Data
requests>=2.31.0
aiohttp>=3.9.0
python-dateutil>=2.8.2

# Ops
structlog>=23.2.0
prometheus-client>=0.19.0
schedule>=1.2.0
tqdm>=4.66.0
```

---

## 4. Structure du projet

```
smartacus/
├── src/
│   ├── data/                          # Couche données
│   │   ├── __init__.py
│   │   ├── data_models.py            # 462 lignes — Modèles Python (ProductData, Snapshot, etc.)
│   │   ├── keepa_client.py           # 1069 lignes — Client Keepa avec rate limiting
│   │   ├── config.py                 # 295 lignes — Configuration centralisée
│   │   └── ingestion_pipeline.py     # 894 lignes — Pipeline d'ingestion
│   │
│   ├── scoring/                       # Moteur de scoring
│   │   ├── __init__.py
│   │   ├── scoring_config.py         # 375 lignes — Seuils et poids
│   │   ├── opportunity_scorer.py     # 915 lignes — Scoring 5 composantes
│   │   ├── economic_scorer.py        # 495 lignes — Score × multiplicateur temps
│   │   └── calibration.py            # 402 lignes — Calibration et backtesting
│   │
│   ├── api/                           # API REST
│   │   ├── __init__.py
│   │   ├── main.py                   # 416 lignes — FastAPI app + endpoints
│   │   ├── models.py                 # 180 lignes — Modèles Pydantic
│   │   ├── services.py              # 731 lignes — Logique métier
│   │   ├── db.py                     # 314 lignes — Pool connexions PostgreSQL
│   │   ├── ai_routes.py             # 369 lignes — Endpoints IA
│   │   └── rag_routes.py            # 292 lignes — Endpoints RAG
│   │
│   ├── events/                        # Détection d'événements
│   │   ├── economic_events.py        # 729 lignes — Détecteur d'événements
│   │   └── event_models.py           # 571 lignes — Modèles d'événements
│   │
│   ├── ai/                            # Intégration LLM
│   │   ├── llm_client.py            # 316 lignes — Client Claude
│   │   ├── thesis_generator.py       # 343 lignes — Génération de thèses
│   │   ├── review_analyzer.py        # 390 lignes — Analyse de reviews
│   │   └── agents/                   # Agents IA
│   │       ├── base.py, discovery.py, analyst.py, sourcing.py, negotiator.py
│   │
│   ├── rag/                           # RAG Knowledge Base
│   │   ├── ingestion.py, chunker.py, embedder.py, retriever.py, models.py
│   │
│   └── orchestrator/                  # Orchestration
│       ├── daily_pipeline.py, scheduler.py, shortlist.py
│       ├── monitoring.py, state.py, logging_config.py
│
├── web/                               # Frontend Next.js
│   ├── src/app/                       # Pages (App Router)
│   ├── src/components/                # 6 composants React
│   ├── src/lib/                       # API client, formatters, mock data
│   ├── src/types/                     # Types TypeScript
│   └── src/hooks/                     # Custom hooks
│
├── scripts/                           # CLI
│   ├── run_controlled.py             # 840 lignes — Pipeline contrôlé (Run 1)
│   ├── run_ingestion.py              # 265 lignes — Ingestion quotidienne
│   ├── test_keepa_connection.py      # 89 lignes — Test Keepa
│   └── test_pipeline_offline.py      # 227 lignes — Test offline
│
├── database/migrations/               # Schéma SQL
│   ├── 001_railway_init.sql          # 859 lignes — Schéma complet
│   ├── 002_pipeline_runs_and_dedup.sql
│   └── 003_quality_gates_and_artifacts.sql
│
├── data/                              # Sorties runtime
│   ├── audit_run_*.json              # Audits de run
│   └── opportunities_run_*.json      # Opportunités scorées
│
└── .env                               # Configuration (non versionné)
```

**Total** : ~12 000+ lignes Python + SQL + TypeScript

---

## 5. Couche Données (src/data)

### 5.1 Modèles de données (data_models.py)

```python
# Hiérarchie des modèles
ProductData                    # Conteneur principal
├── metadata: ProductMetadata  # → table `asins`
├── current_snapshot: ProductSnapshot  # → table `asin_snapshots`
├── price_history: List[PriceHistory]  # Pour analyse de tendance
├── bsr_history: List[BSRHistory]      # Pour BSR trend
└── buybox_history: List[BuyBoxHistory] # Pour rotation vendeurs
```

| Classe | Rôle | Table DB |
|--------|------|----------|
| `ProductMetadata` | Titre, marque, catégorie, images | `asins` |
| `ProductSnapshot` | Prix, BSR, stock, notes, vendeurs | `asin_snapshots` |
| `PriceHistory` | Historique prix (30j) | Analyse in-memory |
| `BSRHistory` | Historique BSR (30j) | Analyse in-memory |
| `StockStatus` | Enum: in_stock, low_stock, out_of_stock... | Type PostgreSQL |
| `FulfillmentType` | Enum: fba, fbm, amazon | Type PostgreSQL |

### 5.2 Client Keepa (keepa_client.py)

```python
class KeepaClient:
    """Client Keepa robuste avec rate limiting intelligent."""

    # Rate Limiting
    _rate_limit: RateLimitState  # Tokens tracking interne
    _rate_limit_lock: Lock       # Thread-safe

    # Méthodes principales
    get_category_asins(category_id) → List[str]     # ~5 tokens
    get_product_data(asins, include_history) → List[ProductData]  # ~2 tokens/ASIN
    get_best_sellers(category_id) → List[str]
    health_check() → Dict
    get_stats() → Dict  # tokens restants, requêtes, erreurs
```

**Quirks Keepa v1.4.3** :
- `keepa.KeepaError` n'existe PAS → catch `Exception`
- `best_sellers_query(str(cat_id), domain='US')` pas `category_lookup`
- `api.query()` domain : string `'US'`, pas int `1`
- CSV data : numpy arrays shape (N,2) avec datetime+value
- `stats['current']` est une liste indexée par type de prix

### 5.3 Configuration (config.py)

```python
@dataclass(frozen=True)
class Settings:
    keepa: KeepaConfig        # API key, tokens/min, retries
    database: DatabaseConfig   # Host, port, pool, SSL
    ingestion: IngestionConfig # Category, batch_size, filtres
    logging: LoggingConfig     # Level, format, file
```

### 5.4 Pipeline d'ingestion (ingestion_pipeline.py)

```python
class IngestionPipeline:
    # Découverte
    discover_category_asins() → List[str]          # Keepa best_sellers
    get_asins_needing_update(asins) → List[str]    # Filtre fraîcheur

    # Batch processing
    fetch_product_batch(asins) → List[ProductData]  # Keepa product query
    upsert_asin_metadata(products) → int            # INSERT/UPDATE asins
    insert_snapshots(products, session_id) → int    # INSERT snapshots (triggers!)

    # Maintenance
    refresh_materialized_views()                     # REFRESH CONCURRENTLY
    close()                                          # Ferme pool DB
```

---

## 6. Moteur de Scoring (src/scoring)

### 6.1 Scoring de base (opportunity_scorer.py)

**Formule** : 5 composantes additives, 100 points max.

```
Score Total = Margin(30) + Velocity(25) + Competition(20) + Gap(15) + TimePressure(10)
```

| Composante | Max | Ce qu'elle mesure |
|-----------|-----|-------------------|
| **Margin** | 30 | Marge nette après FBA fees, PPC, retours |
| **Velocity** | 25 | BSR absolu + deltas 7j/30j + reviews/mois |
| **Competition** | 20 | Nombre vendeurs FBA + rotation BuyBox |
| **Gap** | 15 | Gap reviews vs top 10 + % avis négatifs |
| **TimePressure** | 10 | Ruptures stock + accélération BSR + volatilité prix |

**Règle critique** : `time_pressure < 3` → rejet automatique (`invalid_no_window`)

### 6.2 Gating vs Ranking — deux rôles du temps

Le scoring utilise le temps à deux niveaux distincts, qu'il ne faut pas confondre :

| Concept | Où | Rôle | Question posée |
|---------|-----|------|---------------|
| **TimePressure** (composante, 0-10) | `opportunity_scorer.py` | **Gating** : existe-t-il une fenêtre ? | "Y a-t-il une urgence qui rend cette opportunité actionnable ?" |
| **time_multiplier** (×0.5–2.0) | `economic_scorer.py` | **Ranking** : à quelle vitesse la fenêtre se ferme-t-elle ? | "À valeur égale, laquelle traiter en premier ?" |

- **TimePressure < 3** → rejet. Le produit n'a aucun signal temporel exploitable (`invalid_no_window`).
- **time_multiplier** amplifie ou atténue la valeur économique. Un produit score 65 avec fenêtre 14j (`×1.5`) rank au-dessus d'un score 70 avec fenêtre 120j (`×0.7`).

En résumé : **TimePressure filtre, time_multiplier priorise.**

### 6.3 Scoring économique (economic_scorer.py)

**Formule** : base_score × time_multiplier

```python
# Le temps N'EST PAS un composant additif
# Le temps EST un MULTIPLICATEUR de la valeur d'opportunité
final_score = int(base_score × time_multiplier × 100)  # [0-100]
```

**Multiplicateur temporel** : moyenne géométrique de 4 facteurs, clampée [0.5 – 2.0]

```python
time_multiplier = (stockout_factor × churn_factor × volatility_factor × bsr_factor) ^ 0.25
```

| Facteur | Seuils | Multiplicateur |
|---------|--------|---------------|
| Stockout freq | ≥3/mois → 1.5, ≥1 → 1.2, ≥0.5 → 1.0, <0.5 → 0.8 |
| Seller churn | >30% → 1.4, >20% → 1.2, >10% → 1.0, <10% → 0.8 |
| Price volatility | >20% → 1.3, >10% → 1.1, ≤10% → 1.0 |
| BSR acceleration | >10% → 1.4, >0% → 1.2, >-5% → 1.0, <-5% → 0.8 |

### 6.4 Fenêtres temporelles

| Window | Jours | Multiplicateur | Action |
|--------|-------|---------------|--------|
| CRITICAL | ≤14 | 2.0× | Agir immédiatement |
| URGENT | 14-30 | 1.5× | Action prioritaire |
| ACTIVE | 30-60 | 1.2× | Fenêtre viable |
| STANDARD | 60-90 | 1.0× | Temps disponible |
| EXTENDED | >90 | 0.7× | Pas d'urgence |

### 6.5 Valeur économique

```python
monthly_profit = (amazon_price - COGS - FBA_fees - referral - PPC - returns) × monthly_units
annual_value = monthly_profit × 12
risk_adjusted_value = annual_value × 0.7
rank_score = risk_adjusted_value × urgency_weight  # Pour le classement
```

---

## 7. API REST (src/api)

### 7.1 Endpoints

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/health` | GET | Santé DB + Keepa + dernier run |
| `/api/observability` | GET | Métriques DB complètes |
| `/api/shortlist` | GET | Top N opportunités (DB → demo fallback) |
| `/api/shortlist/export` | GET | Export CSV avec filtres |
| `/api/pipeline/status` | GET | Statut du pipeline |
| `/api/pipeline/run` | POST | Lancer un run pipeline |
| `/api/maintenance/cleanup` | POST | Nettoyage events + VACUUM |
| `/api/maintenance/refresh-views` | POST | Refresh mat views |
| `/api/ai/status` | GET | Statut services IA |
| `/api/ai/thesis` | POST | Générer thèse économique |
| `/api/ai/agent/present-opportunity` | POST | Initialiser conversation agent |
| `/api/ai/agent/message` | POST | Message à un agent |

### 7.2 ShortlistService (services.py)

```python
class ShortlistService:
    def get_shortlist(max_items, min_score, min_value) → ShortlistResponse:
        # 1. Essaie la DB (opportunity_artifacts)
        opportunities = self._get_db_opportunities(max_items, min_score, min_value)
        # 2. Fallback données demo si DB vide
        if not opportunities:
            opportunities = self._get_demo_opportunities(max_items)
        # 3. Construit la réponse
        return ShortlistResponse(summary=..., opportunities=...)
```

### 7.3 Modèles Pydantic (models.py)

```python
class OpportunityModel(BaseModel):
    rank: int
    asin: str
    title: Optional[str]
    brand: Optional[str]
    finalScore: int           # alias: final_score
    baseScore: float          # alias: base_score
    timeMultiplier: float     # alias: time_multiplier
    estimatedMonthlyProfit: float
    estimatedAnnualValue: float
    riskAdjustedValue: float
    windowDays: int
    urgencyLevel: UrgencyLevel
    urgencyLabel: str
    thesis: str
    actionRecommendation: str
    componentScores: Dict[str, ComponentScoreModel]
    economicEvents: List[EconomicEventModel]
    amazonPrice: Optional[float]
    reviewCount: Optional[int]
    rating: Optional[float]
    detectedAt: datetime

    class Config:
        populate_by_name = True  # Accepte snake_case ET camelCase
```

### 7.4 Connexion DB (db.py)

```python
# Pool lazy singleton (psycopg2 ThreadedConnectionPool)
get_pool() → ThreadedConnectionPool
get_connection() → ContextManager  # with get_connection() as conn: ...

# Opérations
check_health() → Dict
create_pipeline_run(triggered_by, config) → str  # → run_id
update_pipeline_run(run_id, status, metrics...)
get_latest_pipeline_run() → Optional[Dict]
run_maintenance(retention_days) → Dict
refresh_materialized_views() → Dict
```

---

## 8. Frontend (web/)

### 8.1 Architecture

```
Next.js 14 (App Router)
├── Layout (layout.tsx)           # HTML shell
├── Page (page.tsx)               # Dashboard principal
│   ├── State: shortlist, filters, selectedOpportunity, agentChat
│   ├── useEffect: fetch API data on mount
│   └── useMemo: filteredOpportunities
│
├── Components
│   ├── Header               # Logo + pipeline status
│   ├── OpportunityCard       # Carte dans la liste
│   ├── OpportunityDetail     # Panneau détail (sticky)
│   ├── ScoreRing             # Cercle SVG score
│   ├── UrgencyBadge          # Badge urgence coloré
│   └── AgentChat             # Modal chat IA
│
├── Lib
│   ├── api.ts                # Client REST (snake→camelCase transform)
│   ├── format.ts             # Formatters (prix, dates, nombres)
│   └── mockData.ts           # Données demo (fallback)
│
└── Types
    └── opportunity.ts        # Interfaces TypeScript
```

### 8.2 Flux de données frontend

```
mount → useEffect
  ├── api.getShortlist({ maxItems: 10 })  →  /api/shortlist?max_items=10
  └── api.getPipelineStatus()              →  /api/pipeline/status
      │
      ▼ Succès → dataSource='api', bandeau vert "Connecté"
      ▼ Erreur → dataSource='mock', bandeau jaune "Mode démo"
      │
      ▼ shortlistData → filteredOpportunities (useMemo)
      │
      ▼ Rendu: OpportunityCard[] + filtres + export CSV
```

### 8.3 Design System (Tailwind)

| Token | Couleur | Usage |
|-------|---------|-------|
| primary-50..900 | Bleu | Boutons, liens, sélection |
| critical | #dc2626 | Urgence critique |
| urgent | #f97316 | Urgence haute |
| active | #eab308 | Fenêtre active |
| standard | #22c55e | Temps disponible |
| extended | #6b7280 | Pas d'urgence |

### 8.4 Proxy API

```javascript
// next.config.js
rewrites: [{
  source: '/api/:path*',
  destination: 'http://localhost:8000/api/:path*'
}]
```

---

## 9. Base de données

### 9.1 Infrastructure

- **Hébergement** : Railway (PostgreSQL 17.7 managé)
- **Endpoint** : `maglev.proxy.rlwy.net:41051/railway`
- **Extensions** : `pg_trgm` (trigram search), `btree_gin` (multi-index)
- **PAS disponible** : TimescaleDB, pgvector (adaptations faites)

### 9.2 Tables principales

```sql
-- 17 tables au total

asins                    -- Catalogue produits (PK: asin VARCHAR(10))
asin_snapshots           -- Séries temporelles prix/BSR/stock (PK: asin, captured_at)
price_events             -- Événements prix (>5% variation)
bsr_events               -- Événements BSR (>20% variation)
stock_events             -- Événements stock (transitions)
reviews                  -- Reviews Amazon individuelles
review_analysis          -- Analyse NLP des reviews
opportunities            -- Opportunités détectées
pipeline_runs            -- Historique des runs (métriques, DQ gates)
opportunity_artifacts    -- Snapshots scoring immutables (audit)
shortlist_snapshots      -- Historique shortlist (hysteresis)
system_metrics           -- Métriques système
rag_documents            -- Documents knowledge base
rag_chunks               -- Chunks avec embeddings (JSONB)
rag_citations            -- Traçabilité utilisation chunks
```

### 9.3 Schéma des tables clés

#### asins (catalogue produits)
```sql
asin VARCHAR(10) PRIMARY KEY,
title TEXT,              -- NULL pour ASINs morts/délistés (migration 004)
brand VARCHAR(255),
category_id BIGINT,
category_path TEXT[],
is_active BOOLEAN DEFAULT TRUE,
tracking_priority INTEGER DEFAULT 5,
last_seen_at TIMESTAMPTZ, -- Dernière apparition dans une réponse Keepa
-- + 20 autres colonnes (dimensions, images, badges...)
```

#### asin_snapshots (séries temporelles)
```sql
PRIMARY KEY (asin, captured_at),
price_current DECIMAL(10,2),
bsr_primary INTEGER,
stock_status stock_status,
rating_average DECIMAL(2,1),
review_count INTEGER,
-- Deltas calculés par trigger
price_delta DECIMAL(10,2),
price_delta_percent DECIMAL(5,2),
bsr_delta INTEGER,
bsr_delta_percent DECIMAL(5,2)
```

#### opportunity_artifacts (scoring immutable)
```sql
artifact_id UUID PRIMARY KEY,
run_id UUID REFERENCES pipeline_runs,
asin VARCHAR(10), rank INTEGER,
final_score INTEGER, base_score DECIMAL(5,4), time_multiplier DECIMAL(4,3),
component_scores JSONB, time_pressure_factors JSONB,
thesis TEXT, action_recommendation TEXT,
estimated_monthly_profit DECIMAL(12,2),
estimated_annual_value DECIMAL(12,2),
risk_adjusted_value DECIMAL(12,2),
window_days INTEGER, urgency_level VARCHAR(20),
amazon_price DECIMAL(10,2), review_count INTEGER, rating DECIMAL(2,1), bsr_primary INTEGER
```

#### pipeline_runs (audit trail)
```sql
run_id UUID PRIMARY KEY,
status pipeline_run_status,  -- running/completed/degraded/failed
asins_total INTEGER, asins_ok INTEGER, asins_failed INTEGER,
duration_total_ms INTEGER,
keepa_tokens_used INTEGER,
-- Data Quality Gates
dq_price_missing_pct DECIMAL(5,2),
dq_bsr_missing_pct DECIMAL(5,2),
dq_review_missing_pct DECIMAL(5,2),
dq_passed BOOLEAN,
error_rate DECIMAL(5,4),
error_budget_breached BOOLEAN,
shortlist_frozen BOOLEAN,
config_snapshot JSONB
```

### 9.4 Triggers (événements automatiques)

| Trigger | Table | Condition | Action |
|---------|-------|-----------|--------|
| `trg_calculate_deltas` | asin_snapshots | BEFORE INSERT | Calcule price_delta, bsr_delta vs snapshot précédent |
| `trg_generate_price_events` | asin_snapshots | AFTER INSERT | Crée price_event si \|delta\| ≥ 5% |
| `trg_generate_bsr_events` | asin_snapshots | AFTER INSERT | Crée bsr_event si \|delta\| ≥ 20% ou ≥ 10k positions |
| `trg_generate_stock_events` | asin_snapshots | AFTER INSERT | Crée stock_event sur changement de statut |

Tous avec `ON CONFLICT DO NOTHING` pour idempotence.

### 9.5 Vues matérialisées

| Vue | Rafraîchissement | Données |
|-----|-----------------|---------|
| `mv_latest_snapshots` | Après chaque run | Dernier snapshot par ASIN |
| `mv_asin_stats_7d` | Après chaque run | Agrégations 7 jours |
| `mv_asin_stats_30d` | Après chaque run | Agrégations 30j + volatilité + trend |
| `mv_review_sentiment` | Après chaque run | Sentiment reviews 90j |

### 9.6 Indexes (92+)

```
-- Recherche texte
idx_asins_title_trgm (title gin_trgm_ops)
idx_reviews_content_trgm (body gin_trgm_ops)

-- Séries temporelles
idx_snapshots_asin_time (asin, captured_at DESC)
idx_*_events_brin (detected_at USING BRIN)

-- Performance dashboard
idx_snapshots_dashboard_cover (asin, captured_at DESC)
  INCLUDE (price_current, bsr_primary, stock_status, rating_average, review_count)

-- Déduplication events
idx_*_events_dedup (asin, snapshot_before_at, snapshot_after_at) UNIQUE
```

### 9.7 Enums PostgreSQL

```sql
stock_status:       in_stock | low_stock | out_of_stock | back_ordered | unknown
fulfillment_type:   fba | fbm | amazon | unknown
event_severity:     low | medium | high | critical
movement_direction: up | down | stable
opportunity_status: new | reviewing | validated | acted | archived | false_positive
opportunity_type:   price_drop | bsr_surge | stock_out_competitor | ...
sentiment_type:     very_negative | negative | neutral | positive | very_positive
pipeline_run_status: running | completed | degraded | failed | cancelled
```

---

## 10. Pipeline d'ingestion

### 10.1 CLI (run_controlled.py)

```bash
python scripts/run_controlled.py \
  --max-asins 100 \
  --freeze \
  -v \
  --log-file scripts/run1_audit.log
```

| Argument | Description | Défaut |
|----------|-------------|--------|
| `--max-asins N` | Max ASINs à traiter | 100 |
| `--freeze` | Mode observation (pas de promotion shortlist) | True |
| `--no-freeze` | Désactive freeze | False |
| `--skip-discovery` | Utilise ASINs existants en DB | False |
| `--asins A,B,C` | ASINs explicites | None |
| `-v, --verbose` | Logs debug | False |
| `--log-file PATH` | Log dans fichier | None |

### 10.2 Phases d'exécution

```
Phase 0: PRE-FLIGHT
  ├─ Créer pipeline_run en DB
  ├─ Charger configuration
  ├─ Vérifier connexion Keepa (tokens)
  └─ Initialiser scorer

Phase 1: INGESTION CONTRÔLÉE
  Step 1: Discovery       → best_sellers_query (10k ASINs, ~5 tokens)
  Step 2: Filtering       → Filtre fraîcheur + cap max_asins
  Step 3: Fetch           → product_data batch (100 ASINs, ~200 tokens)
  Step 4: DB Insert       → upsert metadata + insert snapshots (triggers!)
  Step 5: Data Quality    → % manquant prix/BSR/reviews, seuil 30%
  Step 6: Scoring         → EconomicScorer pour chaque produit
  Step 6b: Artifacts      → Sauvegarde scores dans opportunity_artifacts
  Step 7: Refresh Views   → REFRESH MATERIALIZED VIEW CONCURRENTLY

Phase 1b: RESULTS & AUDIT
  ├─ Update pipeline_run (status, métriques, DQ gates)
  ├─ Print top 10 + distribution scores
  ├─ Save audit JSON + opportunities JSON
  └─ Print timing breakdown
```

### 10.3 Budget tokens Keepa

```
Plan actuel:        21 tokens/min refill rate
Bucket capacity:    ~200 tokens (configurable via KEEPA_TOKENS_PER_MINUTE)
Discovery:          ~5 tokens
100 ASINs:          ~200 tokens (2/ASIN)
Total Run 1:        ~205 tokens

Si bucket plein (200) → run instantané (~25s réseau)
Si bucket vide (0)   → ~205/21 = ~10 min d'attente avant run
```

**Distinction importante** :

| Concept | Valeur | Source |
|---------|--------|--------|
| `KEEPA_TOKENS_PER_MINUTE` (.env) | 200 | Capacité max du bucket local (rate limiter) |
| Refill rate réel | 21 tokens/min | Contrat Keepa, synchronisé depuis les réponses API |
| `tokens_left` (runtime) | 0–200 | Balance temps réel, décrémentée à chaque appel |

Le client Keepa synchronise `tokens_left` et `refill_rate` depuis chaque réponse API Keepa. Le rate limiter local utilise ces valeurs pour décider quand faire la prochaine requête.


---

## 11. Détection d'événements

### 11.1 Types d'événements

| Type | Seuil déclencheur | Signification |
|------|-------------------|--------------|
| `SUPPLY_SHOCK` | Stockout détecté | Demande non satisfaite |
| `COMPETITOR_COLLAPSE` | Vendeur majeur sorti | Parts à capturer |
| `QUALITY_DECAY` | Reviews négatifs en hausse | Opportunité différenciation |
| `DEMAND_SURGE` | BSR en forte amélioration | Demande croissante |
| `PRICING_ANOMALY` | Prix hors norme | Arbitrage possible |
| `SEASONALITY_SIGNAL` | Pattern saisonnier | Fenêtre timing |

### 11.2 Génération automatique (triggers DB)

Les triggers sur `asin_snapshots` génèrent automatiquement :
- **price_events** : quand |price_delta_percent| ≥ 5%
- **bsr_events** : quand |bsr_delta_percent| ≥ 20% ou |bsr_delta| ≥ 10k
- **stock_events** : sur tout changement de stock_status

Sévérité auto-calculée : critical → high → medium → low

---

## 11bis. Review Intelligence (Voice of Customer)

### Objectif

Transformer les avis Amazon en **spécifications produit actionnables** — pas du sentiment décoratif. Répondre à la question que le scoring seul ne couvre pas : **"Comment battre le produit en place ?"**

### Architecture

```
reviews (DB table, à remplir)
         │
    ┌────┴────────────────────────┐
    ▼                             ▼
ReviewSignalExtractor          (Phase 2: LLM batch)
 (déterministe, lexique)        src/ai/review_analyzer.py
    │                             │
    ▼                             ▼
DefectSignal[]                 FeatureRequest[]
    │                             │
    └──────────┬──────────────────┘
               ▼
    ReviewInsightAggregator
               │
               ▼
    ProductImprovementProfile
    (improvement_score 0-1)
               │
    ┌──────────┼───────────┐
    ▼          ▼           ▼
 ranking    thesis      agents
 bonus     fragment    sourcing
```

### Pipeline d'extraction

| Étape | Méthode | Coût | Dans le run principal ? |
|-------|---------|------|----------------------|
| **A. Filtrage** | rating ≤ 3 + body non vide | 0 | Oui |
| **B. Extraction défauts** | Lexique 9 types × ~90 keywords | 0 | Oui |
| **C. Extraction "I wish"** | 6 regex patterns | 0 | Oui |
| **D. Agrégation** | Profil par ASIN | 0 | Oui |
| **E. LLM "I wish" sémantique** | Claude/OpenAI batch | $$$ | **Non** — job séparé |

### Lexique défauts (Car Phone Mounts)

| Type | Keywords | Poids sévérité |
|------|----------|---------------|
| `mechanical_failure` | broke, snapped, cracked, fell apart... | 0.90 |
| `poor_grip` | slips, falls off, doesn't hold, loose... | 0.85 |
| `durability` | after a month, didn't last, adhesive wore off... | 0.75 |
| `compatibility_issue` | doesn't fit, case too thick, blocks camera... | 0.70 |
| `heat_issue` | overheats, gets hot, blocks airflow... | 0.65 |
| `installation_issue` | hard to install, suction doesn't hold... | 0.60 |
| `vibration_noise` | vibrates, rattles, wobbles... | 0.55 |
| `material_quality` | cheap plastic, feels flimsy, creaks... | 0.50 |
| `size_fit` | too bulky, blocks view, in the way... | 0.40 |

### Formule improvement_score

```python
# severity = base_weight × frequency_factor (capped at 1.0)
# frequency_factor = min(1.0, defect_freq / negative_reviews × 2)

defect_score = weighted_avg(top_5_severity) × (0.5 + 0.5 × coverage)
wish_bonus = min(0.2, count(wishes with 3+ mentions) × 0.1)
improvement_score = min(1.0, defect_score + wish_bonus)
```

| Score | Interprétation |
|-------|---------------|
| > 0.7 | Forte opportunité d'amélioration — défauts clairs et corrigeables |
| 0.4–0.7 | Amélioration possible — différenciation modérée |
| < 0.4 | Peu de marge de différenciation par les reviews |

### Connexion au système existant

| Composant | Utilisation de improvement_score |
|-----------|--------------------------------|
| **Ranking** | `rank_score += improvement_score × 0.2 × risk_adjusted_value` (bonus, PAS dans base_score) |
| **Thèse économique** | Fragment auto-généré : "43% des avis négatifs mentionnent 'poor_grip'" |
| **Agent Sourcing** | Checklist auto : "test suction force", "compatibilité iPhone Pro Max + coque" |
| **Agent Analyst** | "Voici les 3 défauts majeurs à corriger pour battre ce produit" |

### Règle de respect du gap_score (15 max)

L'improvement_score **ne modifie PAS** le gap_score du base_score.
Il agit comme un **bonus de ranking** sur le `rank_score` (après calcul du score final).
Cela respecte le plafond de 15 points du composant gap.

### Tables SQL (migration 005)

| Table | Rôle |
|-------|------|
| `review_defects` | Défauts extraits par ASIN (déterministe) |
| `review_feature_requests` | Features manquantes (regex V1, LLM V2) |
| `review_improvement_profiles` | Profil agrégé par ASIN + run (UNIQUE) |

### Module Python

```
src/reviews/
├── __init__.py
├── review_models.py       # DefectSignal, FeatureRequest, ProductImprovementProfile
├── review_signals.py      # ReviewSignalExtractor (lexique + regex)
└── review_insights.py     # ReviewInsightAggregator (profil + DB save)
```

### Backfill Reviews

La table `reviews` se remplit via `scripts/run_reviews_backfill.py` — job **séparé** du pipeline principal.

**Sources supportées** :
| Source | Commande | Usage |
|--------|----------|-------|
| CSV import | `--source csv --csv-file data/reviews.csv` | Testing, données tierces |
| Playwright | `--source playwright --top-n 20` | Headless Chromium (anti-bot) |

**NOT Keepa** : l'API Keepa ne fournit que des métriques agrégées (count, rating, historique) — pas le texte individuel des reviews.

**Options CLI** :
```bash
python scripts/run_reviews_backfill.py --top-n 20                    # top 20 ASINs
python scripts/run_reviews_backfill.py --asins B08L5TNJHG,B0F4MSXW3J  # ASINs spécifiques
python scripts/run_reviews_backfill.py --source csv --csv-file data/reviews_export.csv
python scripts/run_reviews_backfill.py --dry-run                     # preview sans fetch
```

**Garde-fous** :
- `--max-reviews-per-asin 200` : cap par ASIN
- `--max-total 5000` : cap global par run
- `--freshness-hours 168` : skip si reviews < 7 jours (incrémental)
- Idempotent : `ON CONFLICT (review_id) DO UPDATE` (dedup natif)
- Per-ASIN error handling : un ASIN en échec ne casse pas le run

**Post-backfill** : lance automatiquement Review Intelligence (Step 6c) sur les ASINs backfillés. Le pipeline principal (`run_controlled.py`) active aussi Step 6c dès que `reviews` n'est plus vide.

### Qualité Reviews (métriques backfill)

| Métrique | Description |
|----------|-------------|
| `reviews_fetched` | Total reviews récupérées |
| `reviews_inserted` | Nouvelles reviews insérées |
| `reviews_updated` | Reviews existantes mises à jour |
| `reviews_duplicate_pct` | % de doublons (updated/fetched) |
| `asins_failed` | ASINs en échec (0 reviews) |
| `status` | `completed` / `degraded` / `failed` |

### defect_type Enum (Postgres)

Migration 006 : la colonne `review_defects.defect_type` est maintenant un **enum Postgres** (`defect_type_enum`) au lieu de TEXT libre. Empêche le drift de nomenclature.

```sql
CREATE TYPE defect_type_enum AS ENUM (
    'mechanical_failure', 'poor_grip', 'installation_issue',
    'compatibility_issue', 'material_quality', 'vibration_noise',
    'heat_issue', 'size_fit', 'durability'
);
```

---

## 12. IA et Agents

### 12.1 Architecture agents

```
┌─────────────────────────────────────────┐
│              Agent Chat (Frontend)       │
│  ┌─────────┐ ┌────────┐ ┌──────────┐   │
│  │Discovery│ │Analyst │ │Sourcing  │   │
│  │   🔍    │ │   📊   │ │   🏭     │   │
│  └────┬────┘ └────┬───┘ └────┬─────┘   │
│       └───────────┼──────────┘          │
└───────────────────┼─────────────────────┘
                    │ POST /api/ai/agent/message
                    ▼
┌─────────────────────────────────────────┐
│           Backend Agent Router           │
│  sessionId → context → agent → response │
└───────────────────┬─────────────────────┘
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     ┌─────────┐ ┌───────┐ ┌────────┐
     │ Claude  │ │OpenAI │ │  RAG   │
     │(Thesis) │ │(Chat) │ │(Rules) │
     └─────────┘ └───────┘ └────────┘
```

### 12.2 Types d'agents

| Agent | Rôle | Déclencheur |
|-------|------|-------------|
| **Discovery** 🔍 | Qualification d'opportunité | Bouton "Analyser avec l'IA" |
| **Analyst** 📊 | Analyse approfondie | Transition depuis Discovery |
| **Sourcing** 🏭 | Accompagnement fournisseurs | Bouton "Lancer le sourcing" |
| **Negotiator** 🤝 | Aide à la négociation | Transition depuis Sourcing |

---

## 13. RAG (Retrieval-Augmented Generation)

### 13.1 Architecture RAG

```
Document → Chunker (512 tokens) → Embedder (JSONB) → PostgreSQL
                                                        │
Query → Embedder → Similarity Search → Top-K chunks → LLM + Context
```

### 13.2 Tables RAG

| Table | Rôle |
|-------|------|
| `rag_documents` | Métadonnées documents (type, domaine, dates) |
| `rag_chunks` | Chunks avec embeddings (JSONB, prêt pour pgvector) |
| `rag_citations` | Traçabilité utilisation (session, agent, query) |

**Types de documents** : rules, ops, templates, memory

**Note** : Embeddings stockés en JSONB (pas pgvector). Migration vers `vector(1536)` prévue quand Railway supporte pgvector.

### 13.3 Règles de sécurité RAG (anti-bruit)

| Règle | Valeur | Raison |
|-------|--------|--------|
| **Max chunks injectés** | K = 6 | Au-delà, le LLM dilue et invente |
| **Filtrage metadata obligatoire** | `doc_type`, `domain`, `marketplace`, `lang` | Évite d'injecter des règles FR dans un contexte US |
| **Citations obligatoires** | Chaque réponse agent RAG → `rag_citations` | Traçabilité, auditabilité, détection d'hallucination |
| **Score de similarité minimal** | > 0.7 (cosine) | Pas de chunks "vaguement liés" |
| **TTL des chunks** | Re-embedding si `updated_at` > 30j | Évite les données stales |

**Principe** : le RAG ne doit jamais donner au LLM plus de contexte que nécessaire. Un agent qui ne trouve pas de chunk pertinent doit répondre "je n'ai pas d'information fiable" plutôt qu'halluciner.

---

## 14. Orchestration & Monitoring

### 14.1 Pipeline quotidien

```python
# scripts/run_ingestion.py
Modes:
  --mode full           # Discover + filter + fetch
  --mode incremental    # Fetch ASINs existants uniquement
  --mode health         # Vérification santé
  --mode stats          # Afficher statistiques
```

### 14.2 Monitoring (pipeline_runs)

Chaque run enregistre :

| Métrique | Description |
|----------|-------------|
| `duration_*_ms` | Timing par phase (ingestion, events, scoring, refresh) |
| `asins_total/ok/failed` | Compteurs d'exécution |
| `error_rate` | asins_failed / asins_total |
| `error_budget_breached` | error_rate ≥ 10% |
| `dq_*_missing_pct` | % données manquantes (prix, BSR, reviews) |
| `dq_passed` | Tous seuils DQ < 30% |
| `keepa_tokens_used` | Consommation API |
| `config_snapshot` | Configuration utilisée (JSONB) |

### 14.3 Maintenance

```sql
-- Nettoyage (cleanup_old_events)
DELETE FROM price_events WHERE detected_at < NOW() - retention;
DELETE FROM bsr_events WHERE detected_at < NOW() - retention;
DELETE FROM stock_events WHERE detected_at < NOW() - retention;
DELETE FROM opportunities WHERE status = 'archived' AND updated_at < NOW() - retention;
VACUUM ANALYZE;

-- Refresh views
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_snapshots;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_asin_stats_7d;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_asin_stats_30d;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_review_sentiment;
```

### 14.4 SLO & Failure Modes

#### Service Level Objectives

| SLO | Cible | Mesure |
|-----|-------|--------|
| **Durée run** | < 5 min (100 ASINs) | `duration_total_ms` dans `pipeline_runs` |
| **Data Quality** | DQ pass obligatoire | `dq_passed = TRUE` (prix < 30%, BSR < 30%, reviews < 30% manquants) |
| **Error budget** | < 10% d'ASINs en erreur | `error_rate < 0.10` dans `pipeline_runs` |
| **Disponibilité API** | /shortlist répond < 2s | Latence p99 (à instrumenter) |
| **Fraîcheur données** | < 24h depuis dernier run OK | `pipeline_runs.completed_at` |

#### Failure Modes et réactions

| Statut pipeline | Condition | Réaction |
|----------------|-----------|----------|
| `completed` | DQ pass + error_rate < 10% | Shortlist mise à jour, artifacts sauvés |
| `degraded` | DQ pass MAIS error_rate ≥ 10% | **Shortlist NON mise à jour** (freeze automatique). Artifacts sauvés pour audit. Alerte à déclencher |
| `failed` | Crash ou DQ fail | **Rien n'est écrit**. Shortlist précédente reste active. Alerte critique |
| `cancelled` | Interruption manuelle | Pas de conséquence |

#### Règle de protection shortlist

```
SI pipeline.status = 'degraded' OU 'failed'
   → shortlist_frozen = TRUE
   → L'API /shortlist sert les données du DERNIER run 'completed'
   → Pas d'écrasement des artifacts précédents
```

Cette protection est déjà implémentée via `error_budget_breached` et `shortlist_frozen` dans `pipeline_runs`.

---

## 15. Flux de données complet

```
                    KEEPA API
                       │
                 ┌─────┴─────┐
                 │  Discovery │ (best_sellers_query)
                 │  ~5 tokens │
                 └─────┬─────┘
                       │ 10,000 ASINs
                       ▼
                 ┌───────────┐
                 │  Filter   │ (fraîcheur + cap)
                 └─────┬─────┘
                       │ 100 ASINs
                       ▼
                 ┌───────────┐
                 │  Fetch    │ (product query)
                 │ ~200 tok  │
                 └─────┬─────┘
                       │ 100 ProductData
              ┌────────┼────────┐
              ▼        ▼        ▼
         ┌────────┐ ┌──────┐ ┌──────────┐
         │ Upsert │ │Insert│ │  Score   │
         │Metadata│ │Snaps │ │(Economic)│
         │(asins) │ │      │ │          │
         └────────┘ └──┬───┘ └────┬─────┘
                       │          │
                 ┌─────┘          │
                 │ TRIGGERS       │
           ┌─────┼─────┐         │
           ▼     ▼     ▼         │
        ┌─────┐┌────┐┌─────┐    │
        │Price││BSR ││Stock│    │
        │Event││Evt ││Event│    │
        └─────┘└────┘└─────┘    │
                                │
                       ┌────────┘
                       ▼
              ┌──────────────┐
              │  Artifacts   │ (opportunity_artifacts)
              │  100 scored  │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ Refresh MVs  │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ Audit JSON   │ + pipeline_run DB
              └──────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ API /shortlist│ → Frontend
              └──────────────┘
```

---

## 16. Sécurité & Configuration

### 16.1 Variables d'environnement

```bash
# Keepa (requis)
KEEPA_API_KEY=<key>
KEEPA_TOKENS_PER_MINUTE=200  # Bucket capacity, NOT refill rate (refill = 21/min from plan)

# Database (requis)
DATABASE_HOST=maglev.proxy.rlwy.net
DATABASE_PORT=41051
DATABASE_NAME=railway
DATABASE_USER=postgres
DATABASE_PASSWORD=<password>
DATABASE_SSL_MODE=require

# Ingestion
INGESTION_CATEGORY_NODE_ID=7072562011  # Car Phone Mounts
INGESTION_BATCH_SIZE=100

# API
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 16.2 Bonnes pratiques sécurité

- `.env` non versionné (`.gitignore`)
- Connexion DB via SSL (require)
- Pas de credentials dans le code
- Pool de connexions (pas de connexions longues)
- Rate limiting Keepa côté client

---

## 17. Performance & Optimisations

### 17.1 Base de données

| Optimisation | Impact |
|-------------|--------|
| BRIN indexes sur timestamps events | Réduction I/O séries temporelles |
| Covering indexes (INCLUDE) | Évite heap access pour dashboard |
| Partial indexes (WHERE) | Cible les données actives |
| GIN indexes JSONB/arrays | Recherche rapide dans JSON |
| 4 parallel workers | Grandes tables |
| Déduplication events (UNIQUE) | Idempotence pipeline |
| Mat views CONCURRENTLY | Pas de lock en lecture |

### 17.2 API

| Optimisation | Impact |
|-------------|--------|
| Connection pool (2-10) | Réutilisation connexions |
| DB fallback → mock data | Graceful degradation |
| Pydantic v2 (Rust core) | Sérialisation rapide |

### 17.3 Pipeline

| Optimisation | Impact |
|-------------|--------|
| Batch 100 ASINs/requête | 1 appel Keepa au lieu de 100 |
| Rate limiter intelligent | Évite token exhaustion |
| Exponential backoff | Retry robuste |
| Freeze mode | Pas d'écriture shortlist |

### 17.4 Benchmarks Run 1

```
Discovery:    0.1s ( 0.6%)   — 10k ASINs
Filtering:    3.9s (15.7%)   — Requête DB freshness
Fetch:       14.6s (59.0%)   — 100 ASINs Keepa
DB Insert:    1.1s ( 4.6%)   — 100 metadata + 100 snapshots
Scoring:      0.0s ( 0.1%)   — 100 scores
Refresh:      1.0s ( 3.9%)   — 4 mat views
TOTAL:       24.8s
```

---

## 18. Décisions architecturales

| Décision | Justification | Alternative rejetée |
|----------|--------------|-------------------|
| Scoring déterministe (pas de ML) | Explicabilité, reproductibilité, pas de training data | ML/Neural scoring |
| Temps = multiplicateur | Un produit score 80 + fenêtre 14j > score 90 + fenêtre 180j | Temps comme composante additive |
| PostgreSQL pur (pas TimescaleDB) | Railway ne supporte pas l'extension | TimescaleDB hypertables |
| Embeddings en JSONB | pgvector non dispo, migration prévue | Stockage fichier |
| Triggers pour events | Automatique, atomique, pas d'oubli | Génération côté application |
| Freeze mode par défaut | Observer avant d'agir, valider le scoring | Promotion directe |
| Mock data fallback (lecture seule) | Frontend consultable sans backend, mais actions désactivées (sourcing, export, IA) avec bannière DEMO explicite | Erreur si backend down |
| Lightweight scorer API | Évite dépendances lourdes (psycopg2) dans le hot path | Import scorer complet |
| run_controlled.py CLI | Contrôle fin, audit trail, pas de scheduler complexe | Cron + orchestrateur |

---

## 19. Résultats Run 1

**Date** : 5 février 2026
**Durée** : 24.8 secondes
**Status** : COMPLETED

| Métrique | Valeur |
|----------|--------|
| ASINs découverts | 10 000 |
| ASINs traités | 100 |
| Products fetched | 100/100 (100%) |
| Snapshots insérés | 100 |
| Scores calculés | 100 |
| Erreurs | 0 (0%) |
| Tokens Keepa | 210 |
| DQ Gate | PASS |
| Prix manquants | 12% |
| Reviews manquants | 2% |

### Distribution des scores

```
  0-19:   0
 20-39:  24  ########################
 40-59:  69  #####################################################################
 60-79:   7  #######
80-100:   0
```

### Top 5 opportunités

| # | Score | Window | Profit/an | ASIN | Produit |
|---|-------|--------|-----------|------|---------|
| 1 | 72 | 28j | $41,554 | B08L5TNJHG | Lamicall Car Phone Holder |
| 2 | 70 | 28j | $40,055 | B0F4MSXW3J | andobil MagSafe Mount |
| 3 | 68 | 28j | $38,556 | B0DFZXQFYZ | andobil Magnetic Holder |
| 4 | 66 | 45j | $26,297 | B0DGB3FFB6 | Lamicall Car Phone Holder |
| 5 | 63 | 45j | $29,496 | B0DHWPXNBZ | LISEN MagSafe Mount |

---

## 20. Roadmap

### Phase 2 : Auto-niche (planifié)

```
NicheScore = OpportunityDensity × ExpectedValue × TokenEfficiency
```

- `niche_catalog` : catalogue de niches avec métriques
- `niche_runs` : historique par niche
- `token_allocator` : allocation budgétaire multi-niche
- 2-3 niches en production + 1 niche exploratoire
- Rotation automatique basée sur ROI tokens

### Phase 3 : Production

- Scheduler automatique (cron ou schedule)
- Alertes temps réel (WebSocket)
- Authentification utilisateur
- Dashboard analytics avancé
- Export PDF/Excel
- Migration pgvector pour RAG

---

*Document généré automatiquement à partir de l'analyse du codebase Smartacus.*
