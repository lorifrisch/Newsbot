# TODO List - Automated Markets News Brief

## 1. Infrastructure & Configuration
- [x] Basic project structure and file layout.
- [x] Configuration loading from `config.yaml` and `.env` via Pydantic Settings.
- [x] Basic `run_daily.py` (and `run_weekly.py`) entry points.
- [x] Implement robust logging to file and console (`data/logs/`).
- [x] Add `.env.example` file for easier setup.

## 2. News Retrieval (Perplexity API)
- [x] Implement logic to generate research queries based on:
    - Regional coverage (US 70%, EU 20%, China 10%).
    - Watchlist tickers.
- [x] Implement `fetch_news` in `src/retrieval.py` using Perplexity's `sonar` model.
- [x] Add error handling and circuit breaker logic for API calls.

## 3. Analysis & Composition (OpenAI API)
- [x] Define Pydantic models for structured news extraction (FactCard).
- [x] Implement `FactCardExtractor` using OpenAI Strict JSON Schema.
- [x] Integrate Jinja2 templates and analytical composition.

## 4. Data Persistence (SQLite)
- [x] Define database schema for news, fact cards, and reports.
- [x] Implement data storage logic in `src/storage.py` with JSON serialization.
- [x] Implement deduplication via canonical URLs and content hashing.

## 5. Notification (SendGrid)
- [ ] Finalize `send_email` in `src/mail.py`.
- [ ] Add support for HTML/Plain-text multi-part emails.
- [ ] Implement verification of email delivery status.

## 6. Workflow Orchestration
- [ ] Implement Full Daily Brief workflow in `src/main.py`:
    - Retrieve -> Extract -> Save -> Email.
- [ ] Implement Weekly Recap workflow:
    - Query DB for last 7 days -> Summarize -> Save -> Email.
- [ ] Add mechanism to prevent duplicate news across multiple runs.

## 7. Testing & Quality Assurance
- [x] Config loading tests.
- [ ] Mock API responses for Perplexity and OpenAI for unit tests.
- [ ] Add end-to-end integration tests.
- [ ] Coverage reporting.

## 8. Deployment & Automation
- [ ] Finalize `Makefile` for developer experience.
- [ ] Add documentation on how to schedule via `cron` or GitHub Actions.
