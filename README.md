# Smartacus

Sonde economique Amazon — Detection automatique d'opportunites sur la niche **Car Phone Mounts**.

Smartacus collecte des donnees de marche via l'API Keepa, detecte des evenements economiques (supply shock, competitor collapse, quality decay), score les opportunites de maniere deterministe, et genere une shortlist exploitable avec estimations de valeur et fenetres d'action.

## Architecture

```
src/
├── data/              # Ingestion (Keepa API, data models, config)
├── events/            # Detection d'evenements economiques
├── scoring/           # Scoring deterministe + calibration
│   ├── scoring_config.py      # Seuils et ponderations (Car Phone Mounts)
│   ├── opportunity_scorer.py  # Score 0-100 en 5 composantes
│   ├── economic_scorer.py     # Score x multiplicateur temporel
│   └── calibration.py         # Backtesting des seuils
├── orchestrator/      # Pipeline, scheduler, shortlist, state
│   ├── daily_pipeline.py      # Pipeline 5 etapes
│   ├── scheduler.py           # Planification (APScheduler)
│   ├── shortlist.py           # Top 5 opportunities
│   ├── state.py               # Persistence etat (crash recovery)
│   └── logging_config.py      # Logging structure JSON
├── ai/                # Agents IA (discovery, analyst, sourcing, negotiator)
├── rag/               # RAG pipeline (embeddings, retrieval)
└── api/               # FastAPI REST API

web/                   # Frontend Next.js 14 + Tailwind
tests/                 # pytest (106+ tests)
```

## Scoring

Le scoring est **100% deterministe** — memes inputs = meme score, toujours.

| Composante     | Points | Ce que ca mesure                    |
|----------------|--------|-------------------------------------|
| Margin         | 30     | Viabilite economique (marge nette)  |
| Velocity       | 25     | Demande et momentum (BSR, reviews)  |
| Competition    | 20     | Accessibilite du marche             |
| Gap            | 15     | Potentiel d'amelioration produit    |
| Time Pressure  | 10     | Urgence de l'action                 |

**Regle critique** : `time_pressure < 3` → rejet automatique (pas de fenetre d'action).

Le **Economic Scorer** ajoute un multiplicateur temporel (0.5-2.0x) base sur :
- Frequence des ruptures de stock
- Churn des vendeurs
- Volatilite des prix
- Acceleration BSR

## Quick Start

### Backend

```bash
# 1. Configurer l'environnement
cp .env.example .env   # Remplir KEEPA_API_KEY et les credentials DB

# 2. Installer les dependances Python
pip install -r requirements.txt

# 3. Lancer l'API
uvicorn src.api.main:app --reload --port 8000

# API docs: http://localhost:8000/docs
```

### Frontend

```bash
cd web
npm install
npm run dev
# -> http://localhost:3000
```

### Tests

```bash
pytest tests/ -v
```

## API Endpoints

| Methode | Endpoint                  | Description                      |
|---------|---------------------------|----------------------------------|
| GET     | `/api/health`             | Health check                     |
| GET     | `/api/shortlist`          | Shortlist des opportunites       |
| GET     | `/api/shortlist/export`   | Export CSV (avec filtres)        |
| GET     | `/api/pipeline/status`    | Statut du pipeline               |
| POST    | `/api/pipeline/run`       | Declencher un run                |
| POST    | `/api/ai/thesis`          | Generer une these economique     |
| POST    | `/api/ai/agent/message`   | Interagir avec un agent IA       |

### Export CSV

```bash
# Export complet
curl http://localhost:8000/api/shortlist/export -o shortlist.csv

# Avec filtres
curl "http://localhost:8000/api/shortlist/export?urgency=critical,urgent&min_score=60" -o filtered.csv
```

## Calibration

Le module de calibration permet de valider les seuils de scoring sur des cas connus :

```python
from src.scoring.calibration import CalibrationRunner, NICHE_CALIBRATION_CASES

runner = CalibrationRunner()
report = runner.run(NICHE_CALIBRATION_CASES)
print(report.summary())
```

Cela produit un rapport diagnostique (pass rate, biais par composante, cas echoues) sans modifier automatiquement les seuils — la decision de tuning reste humaine.

## Evenements Economiques

Smartacus detecte 3 types d'evenements :

- **Supply Shock** : Ruptures de stock repetees + demande croissante
- **Competitor Collapse** : Churn eleve des vendeurs + sortie du top seller
- **Quality Decay** : Hausse des reviews negatifs + mentions "I wish"

Chaque evenement a une confiance (weak/moderate/strong), une urgence, et des signaux supports/contradictoires.

## Stack

- **Backend** : Python 3.12, FastAPI, psycopg2 (PostgreSQL), APScheduler
- **Frontend** : Next.js 14, TypeScript, Tailwind CSS
- **Data** : Keepa API, PostgreSQL + pgvector
- **AI** : OpenAI GPT, agents multi-etapes
- **Tests** : pytest (106+ tests couvrant events, scoring, integration)

## License

Projet prive.
