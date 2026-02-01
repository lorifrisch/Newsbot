# Markets News Brief 📈

> Automated financial news aggregation and email brief generation system with **sentiment analysis** and **data visualization**.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-130%20passing-brightgreen.svg)]()

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Module Reference](#module-reference)
- [Examples](#examples)
- [API Costs](#api-costs)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

---

## Overview

Markets News Brief is an intelligent financial news aggregation pipeline that:

1. **Retrieves** market news from multiple sources via Perplexity AI
2. **Extracts** structured fact cards using OpenAI GPT-4o
3. **Analyzes sentiment** using VADER (free, local, no API costs)
4. **Ranks** stories by relevance, recency, and market impact
5. **Composes** polished briefs with regional balance (US/EU/China)
6. **Generates** visual charts for email embedding
7. **Delivers** beautiful HTML emails via SendGrid

### Output Examples

**Daily Brief**:
- 5-10 minute reading time
- Regional balance: 70% US, 20% EU, 10% China
- Watchlist ticker coverage
- Market sentiment gauge

**Weekly Recap**:
- 7-day summary compilation
- Top stories by impact
- Trend analysis

---

## Features

| Feature | Description | Cost |
|---------|-------------|------|
| 🔍 **Smart Retrieval** | Perplexity-powered real-time news search | ~$0.01/query |
| 🎯 **Fact Extraction** | Structured extraction: headline, tickers, region | ~$0.02/batch |
| 📊 **Sentiment Analysis** | VADER-based market mood (Bullish/Bearish/Neutral) | **Free** |
| 📈 **Chart Generation** | Sparklines and sentiment gauges | **Free** |
| 🎨 **Regional Balance** | Configurable coverage ratios | — |
| 📧 **Beautiful Emails** | Responsive HTML with dark mode | ~$0.001/email |
| 🗃️ **Deduplication** | SQLite-backed duplicate prevention | **Free** |
| 📆 **Weekly Recaps** | Automated 7-day summaries | — |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Markets News Brief Pipeline                 │
└─────────────────────────────────────────────────────────────────┘

┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Perplexity│ → │  OpenAI  │ → │ Sentiment│ → │  Ranker  │
│ Retrieval │   │ Extract  │    │  VADER   │    │ + Cluster│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
      │               │               │               │
      ▼               ▼               ▼               ▼
  Raw News       Fact Cards      Scored Cards    Ranked Buckets
                                 (compound,       (US/EU/China)
                                  signal)

┌──────────┐    ┌──────────┐    ┌──────────┐
│  OpenAI  │ → │  Charts  │ → │ SendGrid │
│ Compose  │    │ Generate │    │  Email   │
└──────────┘    └──────────┘    └──────────┘
      │               │               │
      ▼               ▼               ▼
  Brief HTML     Sparklines +    Delivered to
  + Summary      Gauges (PNG)    Recipient

┌─────────────────────────────────────────────────────────────────┐
│                         SQLite Storage                           │
│                    (Dedup, Weekly Recap)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Phase 1 - Retrieval**: Perplexity searches for market news based on watchlist tickers
2. **Phase 2 - Extraction**: OpenAI extracts structured fact cards from raw news
3. **Phase 3 - Ranking**: Cards are deduplicated, sentiment-scored, and ranked by region
4. **Phase 4 - Composition**: OpenAI composes a polished brief from ranked cards
5. **Phase 5 - Visualization**: Charts generated (sentiment gauge, sparklines)
6. **Phase 6 - Delivery**: HTML email rendered and sent via SendGrid

---

## Quick Start

### Prerequisites

- Python 3.11+
- API keys for: Perplexity, OpenAI, SendGrid

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd "News worflow"

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Download NLTK data (for sentiment analysis)
python -c "import nltk; nltk.download('vader_lexicon')"
```

### Environment Setup

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
PERPLEXITY_API_KEY=pplx-xxxx
OPENAI_API_KEY=sk-xxxx
SENDGRID_API_KEY=SG.xxxx
```

### First Run

```bash
# Run daily brief
python run_daily.py

# Run weekly recap
python run_weekly.py
```

---

## Configuration

### config.yaml

```yaml
app:
  name: "Markets News Brief"
  brand_name: "Smart Invest"
  log_level: "INFO"          # DEBUG, INFO, WARNING, ERROR

coverage:
  us: 0.7                    # 70% US stories
  eu: 0.2                    # 20% EU stories
  china: 0.1                 # 10% China stories

watchlist:
  tickers:
    - AAPL
    - MSFT
    - GOOGL
    - NVDA
    - TSLA
    - META
    - AMZN
    - SPY
    - QQQ
    - BTC

models:
  retrieval: "pplx-7b-online"  # Perplexity model
  extraction: "gpt-4o"          # OpenAI extraction model
  composition: "gpt-4o"         # OpenAI composition model

email:
  sender: "noreply@yourdomain.com"
  subject_prefix: "[Markets Brief]"
  weekly_subject_prefix: "[Weekly Recap]"
```

### Environment Variables (.env)

| Variable | Description | Required |
|----------|-------------|----------|
| `PERPLEXITY_API_KEY` | Perplexity API key | ✅ |
| `OPENAI_API_KEY` | OpenAI API key | ✅ |
| `SENDGRID_API_KEY` | SendGrid API key | ✅ |
| `RECIPIENT_EMAIL` | Email recipient | ✅ |
| `LOG_LEVEL` | Override log level | ❌ |

---

## Usage

### Daily Brief (Weekdays)

```bash
python run_daily.py
```

**What it does:**
1. Queries Perplexity for latest market news
2. Extracts fact cards via OpenAI
3. Deduplicates against stored cards
4. Scores sentiment (VADER)
5. Ranks by region and relevance
6. Composes brief via OpenAI
7. Generates sentiment gauge chart
8. Sends HTML email

### Weekly Recap (Sundays)

```bash
python run_weekly.py
```

**What it does:**
1. Retrieves fact cards from past 7 days
2. Groups by significance
3. Composes weekly summary
4. Sends recap email

### Dry Run (No Email)

```bash
# Test without sending email
python -c "
from run_daily import main
# Modify to skip email step for testing
"
```

### Command Line Options

```bash
# Run with debug logging
LOG_LEVEL=DEBUG python run_daily.py

# Run for specific date range (weekly)
python run_weekly.py --start 2024-01-01 --end 2024-01-07
```

---

## Module Reference

### Core Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `src/retrieval.py` | Perplexity news fetching | `NewsRetriever.retrieve()` |
| `src/extract.py` | Fact card extraction | `FactExtractor.extract()` |
| `src/sentiment.py` | VADER sentiment analysis | `SentimentAnalyzer`, `analyze_text()` |
| `src/rank.py` | Story ranking | `Ranker.rank()`, `calculate_score()` |
| `src/compose.py` | Brief composition | `BriefComposer.compose()` |
| `src/charts.py` | Chart generation | `ChartGenerator`, `create_sparkline()` |
| `src/mailer.py` | Email delivery | `Mailer.send()` |
| `src/storage.py` | SQLite persistence | `NewsStorage` |

### Sentiment Module (`src/sentiment.py`)

The sentiment module provides market mood analysis using NLTK's VADER lexicon.

**Key Classes:**

```python
@dataclass
class SentimentScore:
    compound: float      # -1.0 (bearish) to +1.0 (bullish)
    positive: float      # Proportion of positive words
    negative: float      # Proportion of negative words
    neutral: float       # Proportion of neutral words
    label: str           # "Bullish", "Bearish", "Neutral", etc.
    
    @property
    def market_signal(self) -> str:
        # Returns emoji: 🟢 🔴 🟡 🟠 ⚪
```

**Usage:**

```python
from src.sentiment import SentimentAnalyzer, analyze_text

# Quick analysis
score = analyze_text("NVIDIA surges 15% on strong AI demand")
print(score.compound)       # 0.599
print(score.label)          # "Bullish"
print(score.market_signal)  # "🟢 Bullish"

# Analyzer instance (with caching)
analyzer = SentimentAnalyzer()
score = analyzer.analyze("Tesla plunges on delivery miss")
print(score.compound)       # -0.494
print(score.market_signal)  # "🔴 Bearish"

# Analyze fact card
fact_card = {"headline": "Fed holds rates steady", "bullets": ["..."]}
score = analyzer.analyze_fact_card(fact_card)

# Compute market mood from multiple cards
mood = analyzer.compute_market_mood([card1, card2, card3])
print(mood["average_compound"])  # 0.35
print(mood["signal"])            # "🟢 Bullish"
```

**Sentiment Scale:**

| Range | Label | Signal |
|-------|-------|--------|
| ≥ 0.3 | Bullish | 🟢 Bullish |
| 0.1 to 0.3 | Slightly Bullish | 🟡 Slightly Bullish |
| -0.1 to 0.1 | Neutral | ⚪ Neutral |
| -0.3 to -0.1 | Slightly Bearish | 🟠 Slightly Bearish |
| ≤ -0.3 | Bearish | 🔴 Bearish |

### Charts Module (`src/charts.py`)

The charts module generates email-safe visualizations using Matplotlib.

**Key Functions:**

```python
from src.charts import (
    create_sparkline,
    create_sentiment_gauge,
    create_mini_bar,
    ChartGenerator,
    SparklineConfig
)

# Sentiment gauge (most common)
gauge_base64 = create_sentiment_gauge(
    score=0.45,           # -1.0 to 1.0
    width=200,
    height=30
)
# Returns: "iVBORw0KGgo..." (base64 PNG)

# Price sparkline
sparkline_base64 = create_sparkline(
    values=[100, 102, 98, 105, 103, 108],
    width=120,
    height=40,
    color_positive="#10B981",  # Green
    color_negative="#EF4444"   # Red
)

# Mini bar chart
bar_base64 = create_mini_bar(
    value=0.15,           # 15% change
    max_value=0.5,
    width=100,
    height=20
)
```

**Embedding in HTML:**

```html
<img src="data:image/png;base64,{{ sentiment_gauge }}" 
     alt="Market Sentiment" 
     style="height: 30px; width: auto;">
```

**Custom Configuration:**

```python
from src.charts import SparklineConfig, ChartGenerator

config = SparklineConfig(
    width=150,
    height=50,
    color_positive="#22C55E",
    color_negative="#DC2626",
    line_width=1.5,
    dpi=100
)

generator = ChartGenerator()
sparkline = generator.create_sparkline([1, 2, 3, 4, 5], config)
```

### Ranking Module (`src/rank.py`)

The ranker scores and groups stories by region with sentiment integration.

**Scoring Formula:**

```
score = recency_score × relevance_score × sentiment_boost
```

Where:
- `recency_score`: 1.0 (today) → 0.5 (3+ days ago)
- `relevance_score`: Based on ticker matches with watchlist
- `sentiment_boost`: 0.95 (neutral) → 1.15 (strong sentiment)

**Usage:**

```python
from src.rank import Ranker

ranker = Ranker(settings)
buckets = ranker.rank(fact_cards)

print(buckets["us"])           # Top US stories
print(buckets["eu"])           # Top EU stories
print(buckets["china"])        # Top China stories
print(buckets["sentiment_summary"])  # Market mood
```

---

## Examples

### Example 1: Analyze Market Sentiment

```python
from src.sentiment import SentimentAnalyzer

analyzer = SentimentAnalyzer()

# Bullish news
score = analyzer.analyze(
    "Apple announces record iPhone sales, stock surges 8% in pre-market trading"
)
print(f"Compound: {score.compound:.3f}")  # 0.765
print(f"Signal: {score.market_signal}")   # 🟢 Bullish

# Bearish news
score = analyzer.analyze(
    "Tesla recalls 500,000 vehicles, shares plunge 12% on safety concerns"
)
print(f"Compound: {score.compound:.3f}")  # -0.682
print(f"Signal: {score.market_signal}")   # 🔴 Bearish

# Neutral news
score = analyzer.analyze(
    "Fed to announce interest rate decision tomorrow at 2pm EST"
)
print(f"Compound: {score.compound:.3f}")  # 0.042
print(f"Signal: {score.market_signal}")   # ⚪ Neutral
```

### Example 2: Generate Email Charts

```python
from src.charts import create_sentiment_gauge, create_sparkline

# Create sentiment gauge for email
gauge = create_sentiment_gauge(score=0.35)
print(f"Gauge size: {len(gauge)} chars")  # ~450 chars

# Create price sparkline
prices = [145.2, 147.8, 146.1, 149.3, 152.0, 150.5, 155.2]
sparkline = create_sparkline(prices)
print(f"Sparkline size: {len(sparkline)} chars")  # ~1400 chars

# Embed in HTML
html = f'''
<div style="display: flex; align-items: center; gap: 10px;">
    <span>Market Mood:</span>
    <img src="data:image/png;base64,{gauge}" alt="Sentiment">
    <span>🟢 Bullish</span>
</div>
'''
```

### Example 3: Full Pipeline (Programmatic)

```python
from src.config import Settings
from src.retrieval import NewsRetriever
from src.extract import FactExtractor
from src.sentiment import SentimentAnalyzer
from src.rank import Ranker
from src.compose import BriefComposer
from src.mailer import Mailer

# Load configuration
settings = Settings.load()

# Phase 1: Retrieve news
retriever = NewsRetriever(settings)
raw_news = retriever.retrieve(date="2024-01-15")

# Phase 2: Extract facts
extractor = FactExtractor(settings)
fact_cards = extractor.extract(raw_news)

# Phase 3: Analyze sentiment
analyzer = SentimentAnalyzer()
for card in fact_cards:
    score = analyzer.analyze_fact_card(card)
    card["sentiment"] = {
        "compound": score.compound,
        "signal": score.market_signal
    }

# Phase 4: Rank stories
ranker = Ranker(settings)
buckets = ranker.rank(fact_cards)

# Phase 5: Compose brief
composer = BriefComposer(settings)
brief = composer.compose(buckets)

# Phase 6: Send email
mailer = Mailer(settings)
mailer.send(
    to="recipient@example.com",
    subject="Markets Brief - Jan 15",
    html=brief["html"]
)
```

### Example 4: Query Historical Data

```python
from src.storage import NewsStorage
from src.config import Settings
from datetime import datetime, timedelta

settings = Settings.load()
storage = NewsStorage(settings.app.database_path)

# Get last 7 days of fact cards
end_date = datetime.now()
start_date = end_date - timedelta(days=7)

cards = storage.get_fact_cards_between(
    start_date.strftime("%Y-%m-%d"),
    end_date.strftime("%Y-%m-%d")
)

print(f"Found {len(cards)} cards from past week")

# Filter by ticker
nvidia_cards = [c for c in cards if "NVDA" in c.get("tickers", [])]
print(f"NVIDIA mentions: {len(nvidia_cards)}")
```

---

## API Costs

### Estimated Costs Per Run

| Service | Usage | Cost |
|---------|-------|------|
| **Perplexity** | ~3-5 queries | ~$0.01-0.02 |
| **OpenAI GPT-4o** | ~2,000-4,000 tokens | ~$0.02-0.04 |
| **SendGrid** | 1 email | ~$0.001 |
| **Sentiment (VADER)** | Local | **Free** |
| **Charts (Matplotlib)** | Local | **Free** |

**Monthly Estimate (Daily + Weekly):**
- ~22 daily runs: $0.66-1.32
- ~4 weekly recaps: $0.08-0.16
- **Total: ~$0.74-1.50/month**

### Cost Optimization Tips

1. Use `gpt-4o-mini` instead of `gpt-4o` for extraction (50% cheaper)
2. Batch Perplexity queries to reduce API calls
3. Increase dedup window to reduce redundant processing

---

## Testing

### Run All Tests

```bash
# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Quick run (no coverage)
pytest tests/ -q

# Verbose output
pytest tests/ -v
```

### Test Modules

| Module | Tests | Coverage |
|--------|-------|----------|
| `test_sentiment.py` | 14 | Sentiment analysis |
| `test_charts.py` | 17 | Chart generation |
| `test_rank.py` | 12 | Ranking algorithm |
| `test_extract.py` | 8 | Fact extraction |
| `test_compose.py` | 6 | Brief composition |
| `test_storage.py` | 10 | Database operations |
| `test_integration.py` | 15 | End-to-end flows |

### Run Specific Tests

```bash
# Sentiment tests only
pytest tests/test_sentiment.py -v

# Charts tests only
pytest tests/test_charts.py -v

# Run single test
pytest tests/test_sentiment.py::TestSentimentAnalyzer::test_analyze_bullish_text -v
```

---

## Deployment

### Cron Setup (macOS/Linux)

```bash
# Edit crontab
crontab -e

# Add entries
# Daily brief at 7:30 AM (Mon-Fri)
30 7 * * 1-5 cd /path/to/project && .venv/bin/python run_daily.py >> data/cron.log 2>&1

# Weekly recap at 9:00 AM (Sunday)
0 9 * * 0 cd /path/to/project && .venv/bin/python run_weekly.py >> data/cron.log 2>&1
```

### Timezone Handling

```cron
# Set timezone explicitly
TZ=Europe/Rome
30 7 * * 1-5 cd /path/to/project && .venv/bin/python run_daily.py >> data/cron.log 2>&1
```

### Verify Cron

```bash
# List cron jobs
crontab -l

# Check cron logs
tail -f data/cron.log
```

### Run Artifacts

Each run creates a timestamped directory:

```
data/runs/
└── 20240115_073000/
    ├── 1_candidates.json      # Perplexity results
    ├── 2_fact_cards.json      # Extracted cards
    ├── 3_composed_brief.json  # Final brief
    ├── 4_email.html           # Rendered email
    └── run.log                # Execution log
```

---

## Troubleshooting

### SendGrid Issues

**Problem**: Email not delivered

```bash
# Verify API key
echo $SENDGRID_API_KEY | head -c 10

# Check SendGrid activity
# Visit: https://app.sendgrid.com/email_activity
```

**Solution**: Ensure sender email is verified in SendGrid.

### Perplexity Issues

**Problem**: "Invalid API key"

```bash
# Test API key
curl https://api.perplexity.ai/chat/completions \
  -H "Authorization: Bearer $PERPLEXITY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"pplx-7b-online","messages":[{"role":"user","content":"test"}]}'
```

### OpenAI Issues

**Problem**: Rate limit exceeded

**Solution**: 
1. Reduce batch size in extraction
2. Add retry logic with exponential backoff
3. Consider using `gpt-4o-mini`

### Sentiment Issues

**Problem**: NLTK data not found

```bash
# Download VADER lexicon
python -c "import nltk; nltk.download('vader_lexicon')"
```

**Problem**: Sentiment always neutral

**Solution**: Check that text contains substantive content (not just tickers/dates).

### Chart Issues

**Problem**: Charts not displaying in email

**Solution**: 
1. Ensure base64 encoding is correct
2. Check email client supports inline images
3. Test with Gmail (best support for base64 images)

### Database Issues

**Problem**: "Database locked"

```bash
# Check for lingering connections
lsof data/news.db

# Vacuum database
sqlite3 data/news.db "VACUUM;"
```

---

## Project Structure

```
News worflow/
├── config.yaml           # Main configuration
├── .env                  # API keys (not in git)
├── .env.example          # Environment template
├── requirements.txt      # Python dependencies
├── run_daily.py          # Daily brief entry point
├── run_weekly.py         # Weekly recap entry point
├── Makefile              # Development commands
├── pytest.ini            # Test configuration
│
├── src/
│   ├── __init__.py
│   ├── config.py         # Settings loader (Pydantic)
│   ├── retrieval.py      # Perplexity news fetching
│   ├── extract.py        # OpenAI fact extraction
│   ├── sentiment.py      # VADER sentiment analysis
│   ├── rank.py           # Story ranking + clustering
│   ├── compose.py        # Brief composition
│   ├── charts.py         # Matplotlib visualizations
│   ├── mailer.py         # SendGrid email delivery
│   ├── storage.py        # SQLite persistence
│   ├── dedup.py          # Duplicate detection
│   ├── clustering.py     # Story grouping
│   ├── openai_client.py  # OpenAI API wrapper
│   ├── perplexity_client.py  # Perplexity API wrapper
│   └── templates/
│       └── email_template.html
│
├── tests/
│   ├── test_sentiment.py
│   ├── test_charts.py
│   ├── test_rank.py
│   ├── test_extract.py
│   ├── test_compose.py
│   ├── test_storage.py
│   └── test_integration.py
│
├── data/
│   ├── news.db           # SQLite database
│   ├── cron.log          # Cron execution logs
│   └── runs/             # Run artifacts
│
└── scripts/              # Utility scripts
```

---

## Appendix A: Prompt Contracts

This section documents the exact prompts used in the pipeline for transparency and debugging.

### A.1 Perplexity Retrieval System Prompt

**Location**: [src/retrieval.py](src/retrieval.py#L99)

```
You are a professional financial news aggregator. 
You must return a raw JSON array of objects. Each object must have:
- title: clear, concise headline
- source: name of the news outlet
- url: full valid URL to the article
- published_at: ISO 8601 date string
- snippet: summary capped at {snippet_words} words
- region: categorical tag as requested in the query

Return ONLY the JSON array. Do not include markdown formatting or preamble.
```

**Query Plan** (6 queries per daily run):
1. `us_macro` - Top 5 US macro and policy news (Fed, inflation, employment)
2. `us_equities` - Top 5 US equity market movers and sector trends
3. `eu_market` - Key Eurozone macro, ECB policy, European stock movers
4. `china_market` - China macro, tech regulation, property market
5. `global_market` - Japan (Yen, Nikkei), SE Asia (TSMC), LatAm (MercadoLibre)
6. `watchlist` - Latest news for configured tickers

### A.2 OpenAI Extraction System Prompt

**Location**: [src/extract.py](src/extract.py#L166)

```
You are a financial fact extraction specialist. Extract structured fact cards from news clusters.

CRITICAL RULES:
1. DO NOT invent or estimate numbers - only use exact figures from the source material
2. Include ALL source URLs in the urls field
3. Keep why_it_matters under 200 characters and focused on market impact
4. Include relevant stock tickers when mentioned (use standard format like AAPL, TSLA)
5. Set confidence based on source quality and data specificity
6. Each fact card must have at least one source and URL
7. Only extract facts with clear market relevance

Output valid JSON only.
```

**FactCard Schema** (enforced via OpenAI Structured Outputs):
```json
{
  "fact_cards": [{
    "story_id": "cluster_id",
    "entity": "Company/Institution/Market",
    "trend": "What is happening",
    "data_point": "Specific number or null",
    "why_it_matters": "Market impact (max 200 chars)",
    "confidence": 0.85,
    "tickers": ["TICKER1"],
    "sources": ["Source Name"],
    "urls": ["https://..."]
  }]
}
```

### A.3 OpenAI Composition Prompt

**Location**: [src/compose.py](src/compose.py#L35)

```
You are a senior financial editor at Bloomberg. Synthesize the following markets data 
into a premium daily brief.

CORE REQUIREMENTS:
1. STYLE: Strictly analytical, professional, and dense. No boilerplate.
2. SOURCES: EVERY bullet must cite sources in brackets like [Source Name].
3. LENGTH: Aim for a comprehensive 5-10 minute read (~1200-1500 words).
4. SENTIMENT: Incorporate sentiment analysis into tone and intro.
5. STRUCTURE: Output JSON with fields:
   - 'headline': Specific, punchy (e.g., "Yields Pivot on Unexpected ISM Cool")
   - 'preheader': 1-sentence teaser
   - 'intro': 3-sentence executive summary
   - 'top5_md': Markdown list of 5 critical stories
   - 'macro_md': 2-3 paragraphs on central banks, rates, macro themes
   - 'watchlist_md': Markdown list for corporate earners
   - 'snapshot_md': Markdown table with Asset, Level/Move, Context

Never hallucinate numbers. Use "not disclosed" or "---" if data is missing.
```

---

## Appendix B: Configuration Reference

### B.1 New Configuration Options (v1.3.0)

**config.yaml additions:**

```yaml
# Token caps for cost control
models:
  extraction_max_tokens: 3000      # Max tokens for fact extraction
  composition_max_tokens: 2048     # Max tokens for daily brief
  weekly_composition_max_tokens: 3000
  use_strict_schema: true          # Use OpenAI structured outputs

# Candidate limits
daily:
  max_candidates: 50               # Total items to retrieve
  snippet_words: 80                # Truncate snippets to N words
  max_clusters: 14                 # Max fact cards to extract

# Sentiment scoring configuration
ranking:
  use_sentiment_boost: true        # Enable/disable sentiment in ranking
  sentiment_boost_range:
    min: 0.95                      # Penalty for neutral content (-5%)
    max: 1.15                      # Boost for strong sentiment (+15%)

# Domain quality filtering
retrieval:
  allowed_domains: []              # Empty = allow all
  # Example: [reuters.com, bloomberg.com, wsj.com, ft.com, cnbc.com]

# Chart embedding method
email:
  chart_embed_method: "cid"        # "cid" (attachment) or "base64" (inline)
```

### B.2 Environment Variables

| Variable | Primary Name | Legacy Name | Required |
|----------|-------------|-------------|----------|
| Email from | `EMAIL_FROM` | `SENDGRID_FROM_EMAIL` | ✅ |
| Email to | `EMAIL_TO` | `RECIPIENT_EMAIL` | ✅ |
| OpenAI API | `OPENAI_API_KEY` | — | ✅ |
| Perplexity API | `PERPLEXITY_API_KEY` | — | ✅ |
| SendGrid API | `SENDGRID_API_KEY` | — | ✅ |

**Precedence**: `EMAIL_FROM` > `SENDGRID_FROM_EMAIL`, `EMAIL_TO` > `RECIPIENT_EMAIL`

---

## Appendix C: Chart Embedding

### C.1 Methods

| Method | Config Value | Reliability | Notes |
|--------|--------------|-------------|-------|
| **CID Attachment** | `cid` | ✅ High | Best for Outlook, Gmail, Apple Mail |
| **Base64 Inline** | `base64` | ⚠️ Medium | May be stripped by some clients |

### C.2 Client Compatibility

| Client | CID | Base64 |
|--------|-----|--------|
| Gmail | ✅ | ✅ |
| Apple Mail | ✅ | ✅ |
| Outlook Desktop | ✅ | ⚠️ |
| Outlook Web | ✅ | ⚠️ |
| Yahoo Mail | ✅ | ⚠️ |

**Recommendation**: Use `chart_embed_method: "cid"` (default) for best cross-client support.

### C.3 Fallback Behavior

The email template includes fallback text if images fail to load:
- Sentiment gauge: Shows signal emoji + text label
- Sparklines: Shows numeric change percentage

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Run tests: `pytest tests/`
4. Commit changes: `git commit -am 'Add feature'`
5. Push: `git push origin feature/my-feature`
6. Create Pull Request

---

## License

MIT License - See LICENSE file for details.

---

## Changelog

### v1.3.0 (Latest)
- ✅ Added extraction retry logic with configurable attempts
- ✅ Implemented OpenAI strict JSON schema for extraction
- ✅ Made sentiment boost configurable (`ranking.use_sentiment_boost`)
- ✅ Added token caps to config (`models.*_max_tokens`)
- ✅ Added domain allowlist for retrieval quality control
- ✅ Implemented SendGrid CID attachments for reliable chart display
- ✅ Standardized environment variables (EMAIL_FROM/EMAIL_TO)
- ✅ Added prompt contracts documentation

### v1.2.0
- ✅ Added VADER sentiment analysis module
- ✅ Added Matplotlib chart generation (sparklines, gauges)
- ✅ Integrated sentiment into ranking algorithm
- ✅ Added market mood section to email template
- ✅ 31 new tests (14 sentiment + 17 charts)

### v1.1.0
- ✅ Weekly recap functionality
- ✅ SQLite deduplication
- ✅ Regional coverage balancing

### v1.0.0
- ✅ Initial release
- ✅ Daily brief generation
- ✅ Perplexity + OpenAI integration
- ✅ SendGrid email delivery

