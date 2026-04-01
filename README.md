# Scraper ARCA

Automatiza la consulta de datos personales (nombre y apellido) en el portal de [ARCA](https://www.arca.gob.ar) (ex-AFIP) usando tus propias credenciales de Clave Fiscal. Funciona como CLI o como servicio REST con soporte para scraping en batch.

## Características

- **CLI**: scrapeá un CUIT y exportá el resultado a CSV con un solo comando
- **API REST**: servicio FastAPI con endpoints para scraping individual y batch concurrente
- **Batch**: hasta 50 CUITs en paralelo, con semáforo configurable
- **CSV export**: salida estructurada con CUIT, nombre, apellido y nombre completo
- **Docker**: imagen lista para producción con Chromium incluido

## Requisitos

- Python 3.12+
- [Playwright](https://playwright.dev/python/) con Chromium instalado

O bien: Docker + Docker Compose.

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Copiá el archivo de ejemplo y completá tus credenciales:

```bash
cp .env.example .env
```

## Variables de entorno

| Variable                  | Default    | Descripción                                      |
|---------------------------|------------|--------------------------------------------------|
| `ARCA_CUIT`               | —          | CUIT/CUIL de 11 dígitos (con o sin guiones)      |
| `ARCA_PASSWORD`           | —          | Contraseña de Clave Fiscal                        |
| `OUTPUT_DIR`              | `output`   | Directorio donde se guardan los CSV              |
| `MAX_CONCURRENT_SCRAPERS` | `5`        | Scrapers simultáneos en el endpoint batch        |

## Uso

### CLI

```bash
# Scraping básico → output/result.csv
python main.py --cuit 20123456789 --password tu_clave

# Ruta de salida personalizada
python main.py --cuit 20123456789 --password tu_clave --output data/resultado.csv

# Ver el navegador (modo no-headless, útil para depurar)
python main.py --cuit 20123456789 --password tu_clave --no-headless

# Guardar capturas de pantalla en debug/ ante un fallo
python main.py --cuit 20123456789 --password tu_clave --debug

# Iniciar el servidor API
python main.py --serve
```

Las credenciales también pueden leerse desde el `.env` o desde variables de entorno del sistema.

### API REST

```bash
python main.py --serve               # http://localhost:8000
python main.py --serve --port 9000   # puerto personalizado
```

Documentación interactiva disponible en `http://localhost:8000/docs`.

#### Endpoints

| Método | Ruta                      | Descripción                          |
|--------|---------------------------|--------------------------------------|
| `GET`  | `/health`                 | Liveness check                       |
| `POST` | `/scrape`                 | Scraping individual (síncrono)       |
| `POST` | `/scrape/batch`           | Batch de hasta 50 CUITs (async)      |
| `GET`  | `/scrape/batch/{job_id}`  | Estado de un job batch               |
| `GET`  | `/download/{job_id}`      | Descarga el CSV de un job completado |

**Scraping individual:**

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"cuit": "20123456789", "password": "tu_clave"}'
```

**Batch:**

```bash
curl -X POST http://localhost:8000/scrape/batch \
  -H "Content-Type: application/json" \
  -d '{
    "credentials": [
      {"cuit": "20123456789", "password": "clave1"},
      {"cuit": "27987654321", "password": "clave2"}
    ]
  }'
```

## Docker

```bash
# Construir y levantar
docker compose up --build

# En background
docker compose up -d --build
```

Los CSV se persisten en `./output` mediante un volumen montado.

Para scraping CLI dentro del contenedor:

```bash
docker compose run --rm arca-scraper \
  python main.py --cuit 20123456789 --password tu_clave
```

## Estructura del proyecto

```
.
├── main.py              # Punto de entrada CLI/servidor
├── src/
│   ├── scraper.py       # Lógica de automatización con Playwright
│   ├── processor.py     # Validación y normalización de datos
│   ├── exporter.py      # Escritura a CSV
│   └── api.py           # FastAPI app
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Aviso legal

Esta herramienta opera exclusivamente con tus propias credenciales de Clave Fiscal sobre tus propios datos. No está diseñada para acceder a datos de terceros. Su uso es responsabilidad del usuario y debe realizarse dentro del marco legal vigente.
