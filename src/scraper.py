import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Response,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)

LOGIN_URL = "https://auth.afip.gob.ar/contribuyente_/login.xhtml"

SEL_CUIT_INPUT = "input#F1\\:username"
SEL_SIGUIENTE_BTN = "input#F1\\:btnSiguiente"
SEL_PASSWORD_INPUT = "input#F1\\:password"
SEL_INGRESAR_BTN = "input#F1\\:btnIngresar"

USER_NAME_SELECTORS = [
    "#usernav strong.text-primary",
    "#usernav strong",
    ".usernav strong",
    "#contenidoInformacionPersonal .nombre",
    ".nombre-usuario",
    "#nombreUsuario",
    "[data-testid='user-name']",
    ".header-user-name",
]

PORTAL_URL_PATTERN = "**/portal/**"
API_PATTERNS = [
    "**/contribuyente/ObtenerDatosPersonales*",
    "**/v1/personas/**",
    "**/getPersona*",
]


@dataclass
class UserInfo:
    cuit: str
    nombre: str
    apellido: str
    full_name: str


class ARCAScraper:
    def __init__(
        self,
        cuit: str,
        password: str,
        headless: bool = True,
        timeout_ms: int = 30_000,
        max_retries: int = 3,
        debug: bool = False,
    ):
        self.cuit = cuit.replace("-", "").strip()
        self.password = password
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.debug = debug

        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "ARCAScraper":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
        )
        return self

    async def __aexit__(self, *_):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def fetch_user_info(self) -> UserInfo:
        last_error: Exception = RuntimeError("No attempts made")

        for attempt in range(1, self.max_retries + 1):
            logger.info("Attempt %d/%d for CUIT %s", attempt, self.max_retries, self.cuit)
            try:
                return await self._run_flow()
            except Exception as exc:
                last_error = exc
                logger.warning("Attempt %d failed: %s", attempt, exc)
                if attempt < self.max_retries:
                    wait = [0.5, 1.0, 1.5][attempt - 1]
                    logger.info("Retrying in %.1fs...", wait)
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"All {self.max_retries} attempts failed for CUIT {self.cuit}"
        ) from last_error

    async def _run_flow(self) -> UserInfo:
        import time
        t0 = time.perf_counter()

        page = await self._context.new_page()
        intercepted_user: Optional[dict] = {}
        _api_ready = asyncio.Event()

        async def _on_response(response: Response):
            for pattern in API_PATTERNS:
                import fnmatch
                if fnmatch.fnmatch(response.url, pattern.replace("**", "*")):
                    try:
                        data = await response.json()
                        logger.debug("Intercepted API response from %s", response.url)
                        intercepted_user.update(data if isinstance(data, dict) else {})
                        _api_ready.set()
                    except Exception:
                        pass

        page.on("response", _on_response)

        try:
            await self._login(page, _api_ready)
            user_info = await self._extract_user(page, intercepted_user)
            elapsed = time.perf_counter() - t0
            logger.info("_run_flow completed in %.2fs for CUIT %s", elapsed, self.cuit)
            return user_info
        finally:
            await page.close()

    async def _login(self, page: Page, api_ready: asyncio.Event) -> None:
        logger.info("Navigating to login page")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)

        logger.info("Entering CUIT")
        await page.wait_for_selector(SEL_CUIT_INPUT, timeout=self.timeout_ms)
        await page.fill(SEL_CUIT_INPUT, self.cuit)
        await page.click(SEL_SIGUIENTE_BTN)

        logger.info("Entering password")
        await page.wait_for_selector(SEL_PASSWORD_INPUT, timeout=self.timeout_ms)
        await page.fill(SEL_PASSWORD_INPUT, self.password)
        await page.click(SEL_INGRESAR_BTN)

        logger.info("Waiting for post-login redirect")
        await page.wait_for_url(
            lambda url: "auth.afip.gob.ar" not in url,
            timeout=self.timeout_ms,
        )
        logger.info("Logged in successfully, current URL: %s", page.url)

        try:
            await asyncio.wait_for(api_ready.wait(), timeout=8.0)
            logger.info("API data intercepted — skipping networkidle wait")
        except asyncio.TimeoutError:
            logger.info("API data not yet available — giving DOM extra time")
            try:
                await page.wait_for_load_state("load", timeout=5_000)
            except PlaywrightTimeoutError:
                logger.warning("load state timeout — proceeding")

    async def _extract_user(
        self, page: Page, intercepted: dict
    ) -> UserInfo:

        nombre, apellido = self._parse_intercepted(intercepted)
        if nombre and apellido:
            logger.info("User info from intercepted API: %s %s", nombre, apellido)
            return UserInfo(
                cuit=self.cuit,
                nombre=nombre,
                apellido=apellido,
                full_name=f"{nombre} {apellido}",
            )

        all_frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for selector in USER_NAME_SELECTORS:
            for frame in all_frames:
                try:
                    await frame.wait_for_selector(selector, timeout=5_000)
                    raw_text = (await frame.inner_text(selector)).strip()
                    logger.debug("Selector '%s' in frame '%s' returned: %s", selector, frame.url, raw_text)
                    nombre, apellido = self._split_full_name(raw_text)
                    if nombre:
                        logger.info("User info from selector '%s': %s", selector, raw_text)
                        return UserInfo(
                            cuit=self.cuit,
                            nombre=nombre,
                            apellido=apellido,
                            full_name=raw_text,
                        )
                except (PlaywrightTimeoutError, Exception):
                    continue

        logger.warning("Falling back to full-page text scan")
        if self.debug:
            await self._dump_debug(page)
        raw_text = await self._scan_page_for_name(page)
        nombre, apellido = self._split_full_name(raw_text)

        if not raw_text:
            raise RuntimeError(
                "Could not locate user name on the page. "
                "The portal layout may have changed."
            )

        return UserInfo(
            cuit=self.cuit,
            nombre=nombre,
            apellido=apellido,
            full_name=raw_text,
        )

    async def _dump_debug(self, page: Page) -> None:
        import os
        os.makedirs("debug", exist_ok=True)
        await page.screenshot(path="debug/portal.png", full_page=True)
        logger.info("Debug screenshot saved to debug/portal.png")
        for i, frame in enumerate(page.frames):
            try:
                html = await frame.content()
                path = f"debug/frame_{i}.html"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"<!-- frame url: {frame.url} -->\n{html}")
                logger.info("Debug frame %d saved to %s (%s)", i, path, frame.url)
            except Exception as exc:
                logger.debug("Could not dump frame %d: %s", i, exc)

    async def _scan_page_for_name(self, page: Page) -> str:
        _JS = """() => {
            // Match "APELLIDO, NOMBRE" (all-caps with comma) OR
            // "Apellido Nombre1 Nombre2" (title-case, no comma, 2+ words)
            const pattern = /^([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ]+ ){1,}[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ]+$|^[A-ZÁÉÍÓÚÜÑ ]+,\\s*[A-ZÁÉÍÓÚÜÑ ]+$/;
            function scan(doc) {
                const texts = [];
                doc.querySelectorAll('*').forEach(el => {
                    el.childNodes.forEach(n => {
                        if (n.nodeType === 3) {
                            const t = n.textContent.trim();
                            if (t) texts.push(t);
                        }
                    });
                });
                return texts.find(t => pattern.test(t)) || '';
            }
            return scan(document);
        }"""

        result: str = await page.evaluate(_JS)
        if result.strip():
            return result.strip()

        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                result = await frame.evaluate(_JS)
                if result.strip():
                    logger.debug("Name found in frame: %s", frame.url)
                    return result.strip()
            except Exception:
                continue

        return ""

    @staticmethod
    def _parse_intercepted(data: dict) -> tuple[str, str]:
        candidates = [
            ("nombre", "apellido"),
            ("primerNombre", "primerApellido"),
            ("nombres", "apellidos"),
            ("name", "lastName"),
        ]
        for nom_key, ape_key in candidates:
            if nom_key in data and ape_key in data:
                return str(data[nom_key]).strip(), str(data[ape_key]).strip()

        for wrapper in ("datosPersonales", "persona", "contribuyente", "data"):
            nested = data.get(wrapper)
            if isinstance(nested, dict):
                for nom_key, ape_key in candidates:
                    if nom_key in nested and ape_key in nested:
                        return str(nested[nom_key]).strip(), str(nested[ape_key]).strip()

        return "", ""

    @staticmethod
    def _split_full_name(full_name: str) -> tuple[str, str]:
        if not full_name:
            return "", ""

        if "," in full_name:
            parts = [p.strip().title() for p in full_name.split(",", 1)]
            apellido, nombre = parts[0], parts[1]
        else:
            words = full_name.strip().title().split()
            apellido = words[0] if words else ""
            nombre = " ".join(words[1:]) if len(words) > 1 else ""

        return nombre, apellido
