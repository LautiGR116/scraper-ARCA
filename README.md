# ARCA Scraper

Python automation for retrieving the authenticated user's name and surname from Argentina's ARCA portal, with a CLI and a FastAPI interface.

The project demonstrates browser automation, structured data extraction, validation and CSV persistence. It uses **Playwright**, rather than Selenium, and is separate from the production systems described in my professional experience.

## How it works

```text
CLI / FastAPI request
        ↓
Playwright browser session → authenticated portal
        ↓
JSON response extraction → DOM/frame fallbacks
        ↓
CUIT checksum validation + name normalization
        ↓
CSV file + structured API response
```

- Async Playwright context management closes browser resources after each scrape.
- Login attempts use configurable retries (three by default).
- Extraction first checks matching JSON responses, then DOM selectors across frames, then a page-text fallback.
- Processing validates the CUIT checksum and required name fields.
- The API writes each result to its own CSV file; the CLI accepts an output path.
- Docker uses a multi-stage build and runs the application as a non-root user.

## Quick start

Requires Python 3.12 and Chromium's system dependencies, or Docker with Compose.

```bash
git clone https://github.com/LautiGR116/scraper-ARCA.git
cd scraper-ARCA
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
cp .env.example .env
```

On Windows, activate the environment with `.venv\Scripts\activate`.

Set `ARCA_PASSWORD` in your local `.env`, then pass your own CUIT explicitly:

```bash
python main.py --cuit YOUR_11_DIGIT_CUIT
python main.py --cuit YOUR_11_DIGIT_CUIT --output output/result.csv
python main.py --cuit YOUR_11_DIGIT_CUIT --no-headless
python main.py --help
```

The CLI reads the password from `--password` or `ARCA_PASSWORD`; using the environment avoids putting it in shell history. Although the example environment file includes `ARCA_CUIT`, the CLI currently requires `--cuit`.

## REST API

```bash
python main.py --serve --host 127.0.0.1
```

Interactive documentation: [http://localhost:8000/docs](http://localhost:8000/docs).

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/health` | Returns `{"status":"ok"}`; does not check the ARCA portal. |
| POST | `/scrape` | Accepts `cuit`, `password` and optional `headless`; waits for scraping to finish. |

Successful responses contain `status: "completed"` and `data` with `cuit`, `nombre`, `apellido` and `full_name`. The normalized full name uses `"Surname, Given name"`. Scraping failures return HTTP 502.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Compose exposes port 8000 and mounts `./output` at `/app/output`. CSV results persist there.

```bash
docker compose run --rm arca-scraper \
  python main.py --cuit YOUR_11_DIGIT_CUIT
```

| Variable | Purpose |
| --- | --- |
| `ARCA_PASSWORD` | CLI password fallback. API requests provide their own password. |
| `OUTPUT_DIR` | API CSV directory; defaults to `output`. The CLI uses `--output`. |

## Code map

| File | Responsibility |
| --- | --- |
| [main.py](main.py) | CLI arguments and server entry point |
| [src/scraper.py](src/scraper.py) | Login, retries and extraction fallbacks |
| [src/processor.py](src/processor.py) | CUIT validation and normalization |
| [src/exporter.py](src/exporter.py) | CSV output |
| [src/api.py](src/api.py) | FastAPI models and routes |

## Scope and limitations

This repository is an automation example, not a production-ready hosted service. The API currently has no authentication, rate limiting or concurrency bound; each request launches a browser. Keep it local or behind appropriate access controls. Portal changes can break extraction, and splitting full names is heuristic.

There is currently no automated test suite in the repository. The commands above describe the implementation; they do not imply a live portal test has been performed.

Use only your own credentials and data. Output CSVs, logs and optional `--debug` screenshots/HTML may contain personal data; keep them out of version control. The tool is not designed to access third-party accounts.

