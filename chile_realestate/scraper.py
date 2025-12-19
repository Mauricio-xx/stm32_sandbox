"""
Scraper para MercadoLibre Chile - Propiedades Inmobiliarias
===========================================================

Este módulo extrae información de listados de propiedades de MercadoLibre Chile
usando Playwright para manejar contenido dinámico y evitar bloqueos.

Datos extraídos:
- Precio (UF o CLP, normalizado)
- Ubicación (Comuna)
- Superficie (m² útiles/totales)
- Gastos Comunes
- Características adicionales (habitaciones, baños, etc.)

Autor: Dashboard MVP Chile Real Estate
Versión: 1.0.0
"""

import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# ESTRUCTURAS DE DATOS
# =============================================================================

class Currency(Enum):
    """Monedas soportadas"""
    UF = "UF"
    CLP = "CLP"
    UNKNOWN = "UNKNOWN"


@dataclass
class ScrapedProperty:
    """
    Datos extraídos de una publicación de MercadoLibre.

    Todos los campos son opcionales para manejar casos donde
    la información no está disponible.
    """
    # Identificación
    url: str
    meli_id: Optional[str] = None
    titulo: Optional[str] = None

    # Precio
    precio_valor: Optional[float] = None
    precio_moneda: Currency = Currency.UNKNOWN
    precio_texto_original: Optional[str] = None

    # Ubicación
    comuna: Optional[str] = None
    region: Optional[str] = None
    direccion: Optional[str] = None

    # Características físicas
    superficie_util: Optional[float] = None      # m² útiles
    superficie_total: Optional[float] = None     # m² totales
    habitaciones: Optional[int] = None
    banos: Optional[int] = None
    estacionamientos: Optional[int] = None
    bodegas: Optional[int] = None
    piso: Optional[int] = None
    antiguedad: Optional[str] = None

    # Gastos
    gastos_comunes: Optional[float] = None       # CLP mensual
    gastos_comunes_texto: Optional[str] = None

    # Metadata
    vendedor: Optional[str] = None
    tipo_vendedor: Optional[str] = None          # Inmobiliaria, Particular, etc.
    fecha_publicacion: Optional[str] = None
    visitas: Optional[int] = None

    # Estado del scraping
    scrape_exitoso: bool = False
    errores: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para serialización"""
        return {
            "url": self.url,
            "meli_id": self.meli_id,
            "titulo": self.titulo,
            "precio": {
                "valor": self.precio_valor,
                "moneda": self.precio_moneda.value,
                "texto_original": self.precio_texto_original
            },
            "ubicacion": {
                "comuna": self.comuna,
                "region": self.region,
                "direccion": self.direccion
            },
            "caracteristicas": {
                "superficie_util_m2": self.superficie_util,
                "superficie_total_m2": self.superficie_total,
                "habitaciones": self.habitaciones,
                "banos": self.banos,
                "estacionamientos": self.estacionamientos,
                "bodegas": self.bodegas,
                "piso": self.piso,
                "antiguedad": self.antiguedad
            },
            "gastos": {
                "gastos_comunes_clp": self.gastos_comunes,
                "texto_original": self.gastos_comunes_texto
            },
            "vendedor": {
                "nombre": self.vendedor,
                "tipo": self.tipo_vendedor
            },
            "metadata": {
                "fecha_publicacion": self.fecha_publicacion,
                "visitas": self.visitas,
                "scrape_exitoso": self.scrape_exitoso,
                "errores": self.errores
            }
        }


# =============================================================================
# UTILIDADES DE PARSING
# =============================================================================

class PriceParser:
    """Utilidades para parsear precios de MercadoLibre Chile"""

    # Patrones para detectar UF
    UF_PATTERNS = [
        r'(\d+(?:[.,]\d+)?)\s*UF',           # "5.000 UF" o "5,000 UF"
        r'UF\s*(\d+(?:[.,]\d+)?)',           # "UF 5.000"
        r'(\d+(?:[.,]\d+)?)\s*U\.F\.',       # "5.000 U.F."
    ]

    # Patrones para detectar CLP
    CLP_PATTERNS = [
        r'\$\s*(\d+(?:\.\d{3})*(?:,\d+)?)',  # "$190.000.000"
        r'(\d+(?:\.\d{3})*)\s*CLP',          # "190.000.000 CLP"
        r'(\d+(?:\.\d{3})*(?:,\d+)?)\s*pesos', # "190.000.000 pesos"
    ]

    @classmethod
    def parse_price(cls, text: str) -> Tuple[Optional[float], Currency]:
        """
        Parsear texto de precio y detectar moneda.

        Args:
            text: Texto del precio (ej: "5.500 UF", "$190.000.000")

        Returns:
            Tuple de (valor numérico, moneda detectada)
        """
        if not text:
            return None, Currency.UNKNOWN

        text = text.strip().upper()

        # Intentar detectar UF
        for pattern in cls.UF_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1)
                value = cls._parse_number(value_str)
                return value, Currency.UF

        # Intentar detectar CLP
        for pattern in cls.CLP_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1)
                value = cls._parse_number(value_str)
                return value, Currency.CLP

        # Fallback: intentar extraer número si hay símbolo $
        if '$' in text:
            numbers = re.findall(r'[\d.,]+', text)
            if numbers:
                value = cls._parse_number(numbers[0])
                if value and value > 100000:  # Probablemente CLP
                    return value, Currency.CLP
                elif value and value < 50000:  # Probablemente UF
                    return value, Currency.UF

        return None, Currency.UNKNOWN

    @classmethod
    def _parse_number(cls, text: str) -> Optional[float]:
        """
        Convertir texto numérico a float.

        Maneja formatos chilenos:
        - "5.500" (miles con punto)
        - "5.500,50" (decimales con coma)
        - "5500.50" (formato internacional)
        """
        if not text:
            return None

        text = text.strip()

        # Detectar si es formato chileno (punto como separador de miles)
        # o formato internacional (punto como decimal)

        # Si tiene coma, la coma es decimal (formato chileno)
        if ',' in text:
            # Remover puntos de miles, reemplazar coma por punto
            text = text.replace('.', '').replace(',', '.')
        else:
            # Si tiene múltiples puntos, son separadores de miles
            if text.count('.') > 1:
                text = text.replace('.', '')
            # Si tiene un punto y el número después es 3 dígitos, es separador de miles
            elif '.' in text:
                parts = text.split('.')
                if len(parts) == 2 and len(parts[1]) == 3:
                    text = text.replace('.', '')

        try:
            return float(text)
        except ValueError:
            return None

    @classmethod
    def parse_gastos_comunes(cls, text: str) -> Optional[float]:
        """
        Parsear gastos comunes (siempre en CLP).

        Ejemplos:
        - "$80.000"
        - "80000"
        - "$80.000 mensual"
        """
        if not text:
            return None

        # Extraer números
        numbers = re.findall(r'[\d.,]+', text)
        if numbers:
            value = cls._parse_number(numbers[0])
            # Gastos comunes típicos están entre 30.000 y 500.000 CLP
            if value and 10000 < value < 1000000:
                return value

        return None


class TextParser:
    """Utilidades para parsear texto de características"""

    @classmethod
    def parse_superficie(cls, text: str) -> Optional[float]:
        """
        Extraer superficie en m².

        Ejemplos:
        - "65 m²"
        - "65m2"
        - "65 metros cuadrados"
        """
        if not text:
            return None

        patterns = [
            r'(\d+(?:[.,]\d+)?)\s*m[²2]',
            r'(\d+(?:[.,]\d+)?)\s*metros?\s*cuadrados?',
            r'(\d+(?:[.,]\d+)?)\s*mts?',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return PriceParser._parse_number(match.group(1))

        # Si es solo un número, asumir que son m²
        try:
            return float(text.strip())
        except ValueError:
            return None

    @classmethod
    def parse_integer(cls, text: str) -> Optional[int]:
        """Extraer entero de texto"""
        if not text:
            return None

        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))
        return None

    @classmethod
    def extract_comuna(cls, location_text: str) -> Optional[str]:
        """
        Extraer comuna de texto de ubicación.

        MercadoLibre típicamente muestra:
        - "Las Condes, Región Metropolitana"
        - "Providencia, Santiago"
        """
        if not location_text:
            return None

        # Tomar la primera parte antes de la coma
        parts = location_text.split(',')
        if parts:
            comuna = parts[0].strip()
            # Limpiar prefijos comunes
            comuna = re.sub(r'^(comuna\s+de\s+|en\s+)', '', comuna, flags=re.IGNORECASE)
            return comuna

        return location_text.strip()


# =============================================================================
# SCRAPER PRINCIPAL
# =============================================================================

class MercadoLibreScraper:
    """
    Scraper para MercadoLibre Chile usando Playwright.

    Características:
    - Maneja contenido dinámico (JavaScript)
    - Rotación de User-Agents
    - Manejo de bloqueos y captchas
    - Extracción robusta con múltiples selectores

    Usage:
        scraper = MercadoLibreScraper()
        property_data = await scraper.scrape(url)
    """

    # User agents para rotación
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]

    # Selectores CSS para MercadoLibre (múltiples opciones por si cambian)
    SELECTORS = {
        # Precio
        "precio": [
            "span.andes-money-amount__fraction",
            ".ui-pdp-price__second-line .andes-money-amount__fraction",
            "[data-testid='price-part'] .andes-money-amount__fraction",
            ".ui-pdp-price .andes-money-amount",
        ],
        "precio_moneda": [
            "span.andes-money-amount__currency-symbol",
            ".ui-pdp-price__second-line .andes-money-amount__currency-symbol",
        ],

        # Título
        "titulo": [
            "h1.ui-pdp-title",
            ".ui-pdp-header__title-container h1",
            "[data-testid='title']",
        ],

        # Ubicación
        "ubicacion": [
            ".ui-pdp-media__title",
            ".ui-vip-location .ui-pdp-media__title",
            "[data-testid='location']",
            ".ui-pdp-header__subtitle",
        ],

        # Características (tabla de specs)
        "specs_table": [
            ".ui-pdp-specs__table",
            ".ui-vip-specs",
            "[data-testid='specs']",
        ],
        "specs_row": [
            ".ui-pdp-specs__table__row",
            ".andes-table__row",
            "tr",
        ],

        # Atributos destacados
        "highlighted_specs": [
            ".ui-pdp-highlighted-specs-res__icon-label",
            ".ui-pdp-highlights__item",
            "[data-testid='highlighted-spec']",
        ],

        # Descripción
        "descripcion": [
            ".ui-pdp-description__content",
            "[data-testid='description']",
        ],

        # Vendedor
        "vendedor": [
            ".ui-pdp-seller__header__title",
            ".ui-box-component__title",
            "[data-testid='seller-name']",
        ],
    }

    # Mapeo de labels a campos
    LABEL_MAPPING = {
        # Superficie
        "superficie útil": "superficie_util",
        "superficie util": "superficie_util",
        "m² útiles": "superficie_util",
        "metros útiles": "superficie_util",
        "superficie total": "superficie_total",
        "m² totales": "superficie_total",
        "superficie": "superficie_util",  # Default

        # Habitaciones
        "dormitorios": "habitaciones",
        "habitaciones": "habitaciones",
        "recámaras": "habitaciones",
        "ambientes": "habitaciones",

        # Baños
        "baños": "banos",
        "baño": "banos",

        # Estacionamientos
        "estacionamientos": "estacionamientos",
        "estacionamiento": "estacionamientos",
        "cocheras": "estacionamientos",

        # Bodegas
        "bodegas": "bodegas",
        "bodega": "bodegas",

        # Piso
        "piso": "piso",
        "nivel": "piso",

        # Antigüedad
        "antigüedad": "antiguedad",
        "antiguedad": "antiguedad",
        "año construcción": "antiguedad",
        "año de construcción": "antiguedad",

        # Gastos comunes
        "gastos comunes": "gastos_comunes",
        "expensas": "gastos_comunes",
        "mantención": "gastos_comunes",
    }

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Inicializar scraper.

        Args:
            headless: Ejecutar browser sin ventana visible
            timeout: Timeout en milisegundos para esperas
        """
        self.headless = headless
        self.timeout = timeout
        self._ua_index = 0

    def _get_user_agent(self) -> str:
        """Obtener User-Agent rotativo"""
        ua = self.USER_AGENTS[self._ua_index % len(self.USER_AGENTS)]
        self._ua_index += 1
        return ua

    def _extract_meli_id(self, url: str) -> Optional[str]:
        """Extraer ID de MercadoLibre de la URL"""
        # Formato: MLC-XXXXXXXXX o MLC-XXXXXXXXXX
        match = re.search(r'(MLC-?\d+)', url)
        if match:
            return match.group(1).replace('-', '')
        return None

    async def scrape(self, url: str) -> ScrapedProperty:
        """
        Scrape de una URL de MercadoLibre.

        Args:
            url: URL completa del listado

        Returns:
            ScrapedProperty con datos extraídos
        """
        result = ScrapedProperty(url=url)
        result.meli_id = self._extract_meli_id(url)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            result.errores.append("Playwright no instalado. Ejecute: pip install playwright && playwright install chromium")
            return result

        try:
            async with async_playwright() as p:
                # Lanzar browser
                browser = await p.chromium.launch(headless=self.headless)

                # Crear contexto con User-Agent
                context = await browser.new_context(
                    user_agent=self._get_user_agent(),
                    viewport={"width": 1920, "height": 1080},
                    locale="es-CL",
                )

                # Nueva página
                page = await context.new_page()

                # Navegar
                logger.info(f"Navegando a: {url}")
                response = await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                if response and response.status >= 400:
                    result.errores.append(f"HTTP Error: {response.status}")
                    await browser.close()
                    return result

                # Esperar a que cargue el contenido principal
                await page.wait_for_timeout(2000)

                # Extraer datos
                await self._extract_titulo(page, result)
                await self._extract_precio(page, result)
                await self._extract_ubicacion(page, result)
                await self._extract_specs(page, result)
                await self._extract_highlighted_specs(page, result)
                await self._extract_vendedor(page, result)

                # Buscar gastos comunes en descripción si no se encontró
                if result.gastos_comunes is None:
                    await self._extract_from_description(page, result)

                result.scrape_exitoso = True

                await browser.close()

        except Exception as e:
            logger.error(f"Error en scraping: {e}")
            result.errores.append(str(e))

        return result

    async def _extract_titulo(self, page, result: ScrapedProperty) -> None:
        """Extraer título de la publicación"""
        for selector in self.SELECTORS["titulo"]:
            try:
                element = await page.query_selector(selector)
                if element:
                    result.titulo = await element.inner_text()
                    return
            except Exception:
                continue

    async def _extract_precio(self, page, result: ScrapedProperty) -> None:
        """Extraer precio y detectar moneda"""
        precio_texto = None
        moneda_texto = None

        # Obtener fracción del precio
        for selector in self.SELECTORS["precio"]:
            try:
                element = await page.query_selector(selector)
                if element:
                    precio_texto = await element.inner_text()
                    break
            except Exception:
                continue

        # Obtener símbolo de moneda
        for selector in self.SELECTORS["precio_moneda"]:
            try:
                element = await page.query_selector(selector)
                if element:
                    moneda_texto = await element.inner_text()
                    break
            except Exception:
                continue

        if precio_texto:
            # Combinar moneda y precio
            full_price = f"{moneda_texto or ''} {precio_texto}".strip()
            result.precio_texto_original = full_price

            # Parsear
            valor, moneda = PriceParser.parse_price(full_price)
            result.precio_valor = valor
            result.precio_moneda = moneda

    async def _extract_ubicacion(self, page, result: ScrapedProperty) -> None:
        """Extraer ubicación"""
        for selector in self.SELECTORS["ubicacion"]:
            try:
                element = await page.query_selector(selector)
                if element:
                    ubicacion_texto = await element.inner_text()
                    result.direccion = ubicacion_texto
                    result.comuna = TextParser.extract_comuna(ubicacion_texto)

                    # Extraer región si está presente
                    parts = ubicacion_texto.split(',')
                    if len(parts) > 1:
                        result.region = parts[-1].strip()

                    return
            except Exception:
                continue

    async def _extract_specs(self, page, result: ScrapedProperty) -> None:
        """Extraer especificaciones de la tabla"""
        try:
            # Buscar tabla de specs
            tables = await page.query_selector_all(".ui-pdp-specs__table, .andes-table")

            for table in tables:
                rows = await table.query_selector_all("tr, .ui-pdp-specs__table__row")

                for row in rows:
                    try:
                        # Obtener label y valor
                        cells = await row.query_selector_all("td, th, span")
                        if len(cells) >= 2:
                            label = (await cells[0].inner_text()).strip().lower()
                            value = (await cells[-1].inner_text()).strip()

                            self._map_spec_to_result(label, value, result)
                    except Exception:
                        continue

        except Exception as e:
            logger.debug(f"Error extrayendo specs: {e}")

    async def _extract_highlighted_specs(self, page, result: ScrapedProperty) -> None:
        """Extraer specs destacados (iconos con metros, habitaciones, etc.)"""
        try:
            elements = await page.query_selector_all(
                ".ui-pdp-highlighted-specs-res__icon-label, "
                ".ui-pdp-highlights__item, "
                ".ui-vip-specs__items-group li"
            )

            for element in elements:
                try:
                    text = await element.inner_text()
                    text_lower = text.lower()

                    # Detectar tipo de spec por contenido
                    if "m²" in text or "m2" in text or "metros" in text_lower:
                        sup = TextParser.parse_superficie(text)
                        if sup and result.superficie_util is None:
                            result.superficie_util = sup

                    elif "dormitorio" in text_lower or "habitacion" in text_lower:
                        result.habitaciones = TextParser.parse_integer(text)

                    elif "baño" in text_lower:
                        result.banos = TextParser.parse_integer(text)

                    elif "estacionamiento" in text_lower:
                        result.estacionamientos = TextParser.parse_integer(text)

                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Error extrayendo highlighted specs: {e}")

    async def _extract_vendedor(self, page, result: ScrapedProperty) -> None:
        """Extraer información del vendedor"""
        for selector in self.SELECTORS["vendedor"]:
            try:
                element = await page.query_selector(selector)
                if element:
                    result.vendedor = await element.inner_text()
                    return
            except Exception:
                continue

    async def _extract_from_description(self, page, result: ScrapedProperty) -> None:
        """Buscar información adicional en la descripción"""
        try:
            for selector in self.SELECTORS["descripcion"]:
                element = await page.query_selector(selector)
                if element:
                    desc_text = await element.inner_text()

                    # Buscar gastos comunes
                    gc_patterns = [
                        r'gastos?\s+comunes?[:\s]*\$?\s*([\d.,]+)',
                        r'expensas?[:\s]*\$?\s*([\d.,]+)',
                        r'mantenci[oó]n[:\s]*\$?\s*([\d.,]+)',
                    ]

                    for pattern in gc_patterns:
                        match = re.search(pattern, desc_text, re.IGNORECASE)
                        if match:
                            gc = PriceParser.parse_gastos_comunes(match.group(1))
                            if gc:
                                result.gastos_comunes = gc
                                result.gastos_comunes_texto = match.group(0)
                                break

                    return
        except Exception as e:
            logger.debug(f"Error extrayendo descripción: {e}")

    def _map_spec_to_result(self, label: str, value: str, result: ScrapedProperty) -> None:
        """Mapear spec de tabla a campo de resultado"""
        label_clean = label.lower().strip()

        for pattern, field in self.LABEL_MAPPING.items():
            if pattern in label_clean:
                if field == "superficie_util":
                    result.superficie_util = TextParser.parse_superficie(value)
                elif field == "superficie_total":
                    result.superficie_total = TextParser.parse_superficie(value)
                elif field in ["habitaciones", "banos", "estacionamientos", "bodegas", "piso"]:
                    setattr(result, field, TextParser.parse_integer(value))
                elif field == "antiguedad":
                    result.antiguedad = value
                elif field == "gastos_comunes":
                    result.gastos_comunes = PriceParser.parse_gastos_comunes(value)
                    result.gastos_comunes_texto = value
                break


# =============================================================================
# FUNCIÓN WRAPPER SÍNCRONA
# =============================================================================

def scrape_mercadolibre(url: str, headless: bool = True) -> ScrapedProperty:
    """
    Wrapper síncrono para scraping de MercadoLibre.

    Args:
        url: URL del listado de MercadoLibre
        headless: Ejecutar sin ventana visible

    Returns:
        ScrapedProperty con datos extraídos

    Usage:
        data = scrape_mercadolibre("https://departamento.mercadolibre.cl/MLC-XXX")
        if data.scrape_exitoso:
            print(f"Precio: {data.precio_valor} {data.precio_moneda.value}")
    """
    scraper = MercadoLibreScraper(headless=headless)
    return asyncio.run(scraper.scrape(url))


# =============================================================================
# FALLBACK: ENTRADA MANUAL
# =============================================================================

@dataclass
class ManualPropertyInput:
    """
    Estructura para entrada manual cuando el scraping falla.

    Proporciona defaults sensatos y validación básica.
    """
    precio_uf: float
    arriendo_clp: float
    gastos_comunes_clp: float = 0.0
    superficie_m2: float = 0.0
    comuna: str = ""
    habitaciones: int = 0
    banos: int = 0
    estacionamientos: int = 0

    def validate(self) -> List[str]:
        """Validar entrada y retornar lista de errores"""
        errors = []

        if self.precio_uf <= 0:
            errors.append("Precio UF debe ser mayor a 0")

        if self.arriendo_clp <= 0:
            errors.append("Arriendo CLP debe ser mayor a 0")

        if self.precio_uf > 100000:
            errors.append("Precio UF parece muy alto (>100,000 UF)")

        if self.arriendo_clp > 10_000_000:
            errors.append("Arriendo parece muy alto (>$10M CLP)")

        return errors

    def to_property_input(self):
        """Convertir a PropertyInput para el motor financiero"""
        from financials import PropertyInput

        return PropertyInput(
            precio_uf=self.precio_uf,
            arriendo_clp=self.arriendo_clp,
            gastos_comunes_clp=self.gastos_comunes_clp,
            superficie_m2=self.superficie_m2,
            comuna=self.comuna
        )


def create_property_from_scraped(
    scraped: ScrapedProperty,
    arriendo_clp: float,
    uf_value: float,
    gastos_comunes_override: Optional[float] = None
):
    """
    Crear PropertyInput desde datos scrapeados.

    Args:
        scraped: Datos del scraping
        arriendo_clp: Arriendo estimado (no se puede scrapear)
        uf_value: Valor actual de la UF para conversiones
        gastos_comunes_override: Override de gastos comunes si scraping falló

    Returns:
        PropertyInput para el motor financiero
    """
    from financials import PropertyInput

    # Convertir precio a UF si es necesario
    precio_uf = scraped.precio_valor
    if scraped.precio_moneda == Currency.CLP and precio_uf:
        precio_uf = precio_uf / uf_value

    # Usar gastos comunes scrapeados o override
    gastos_comunes = gastos_comunes_override or scraped.gastos_comunes or 0.0

    return PropertyInput(
        precio_uf=precio_uf or 0.0,
        arriendo_clp=arriendo_clp,
        gastos_comunes_clp=gastos_comunes,
        superficie_m2=scraped.superficie_util or scraped.superficie_total or 0.0,
        comuna=scraped.comuna or "",
        url=scraped.url
    )


# =============================================================================
# SCRAPER ALTERNATIVO CON REQUESTS (FALLBACK)
# =============================================================================

class RequestsScraper:
    """
    Scraper alternativo usando requests + BeautifulSoup.

    Menos efectivo que Playwright pero funciona sin instalar browsers.
    Útil para casos donde Playwright no está disponible.
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    @classmethod
    def scrape(cls, url: str) -> ScrapedProperty:
        """
        Intentar scraping con requests (puede fallar por bloqueos).
        """
        import requests
        from bs4 import BeautifulSoup

        result = ScrapedProperty(url=url)
        result.meli_id = re.search(r'(MLC-?\d+)', url)
        if result.meli_id:
            result.meli_id = result.meli_id.group(1).replace('-', '')

        try:
            response = requests.get(url, headers=cls.HEADERS, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Título
            title_elem = soup.select_one('h1.ui-pdp-title')
            if title_elem:
                result.titulo = title_elem.get_text(strip=True)

            # Precio
            price_elem = soup.select_one('.andes-money-amount__fraction')
            currency_elem = soup.select_one('.andes-money-amount__currency-symbol')
            if price_elem:
                price_text = f"{currency_elem.get_text() if currency_elem else ''} {price_elem.get_text()}"
                result.precio_texto_original = price_text.strip()
                result.precio_valor, result.precio_moneda = PriceParser.parse_price(price_text)

            # Ubicación
            location_elem = soup.select_one('.ui-pdp-media__title')
            if location_elem:
                loc_text = location_elem.get_text(strip=True)
                result.direccion = loc_text
                result.comuna = TextParser.extract_comuna(loc_text)

            # Características destacadas
            specs = soup.select('.ui-pdp-highlighted-specs-res__icon-label')
            for spec in specs:
                text = spec.get_text(strip=True).lower()
                if 'm²' in text or 'm2' in text:
                    result.superficie_util = TextParser.parse_superficie(text)
                elif 'dormitorio' in text:
                    result.habitaciones = TextParser.parse_integer(text)
                elif 'baño' in text:
                    result.banos = TextParser.parse_integer(text)

            result.scrape_exitoso = True

        except requests.RequestException as e:
            result.errores.append(f"Request error: {e}")
        except Exception as e:
            result.errores.append(f"Parse error: {e}")

        return result


def scrape_with_fallback(url: str, try_playwright: bool = True) -> ScrapedProperty:
    """
    Intentar scraping con Playwright, fallback a requests.

    Args:
        url: URL del listado
        try_playwright: Intentar Playwright primero

    Returns:
        ScrapedProperty con datos extraídos
    """
    if try_playwright:
        try:
            result = scrape_mercadolibre(url, headless=True)
            if result.scrape_exitoso:
                return result
        except Exception as e:
            logger.warning(f"Playwright falló: {e}, intentando requests...")

    # Fallback a requests
    try:
        return RequestsScraper.scrape(url)
    except ImportError:
        result = ScrapedProperty(url=url)
        result.errores.append("BeautifulSoup no instalado. pip install beautifulsoup4")
        return result


# =============================================================================
# DATOS DE EJEMPLO (PARA DESARROLLO/DEMO)
# =============================================================================

def get_sample_property(sample_id: str = "MLC2685598554") -> ScrapedProperty:
    """
    Retorna datos de ejemplo para desarrollo y demos.

    Útil cuando el scraping no funciona (bloqueos, restricciones de red).

    Args:
        sample_id: ID de la propiedad de ejemplo

    Returns:
        ScrapedProperty con datos realistas del mercado chileno
    """
    samples = {
        "MLC2685598554": ScrapedProperty(
            url="https://departamento.mercadolibre.cl/MLC-2685598554",
            meli_id="MLC2685598554",
            titulo="Departamento en Venta, Las Condes, Región Metropolitana",
            precio_valor=5800.0,
            precio_moneda=Currency.UF,
            precio_texto_original="5.800 UF",
            comuna="Las Condes",
            region="Región Metropolitana",
            direccion="Las Condes, Región Metropolitana",
            superficie_util=72.0,
            superficie_total=82.0,
            habitaciones=2,
            banos=2,
            estacionamientos=1,
            bodegas=1,
            gastos_comunes=95000.0,
            gastos_comunes_texto="$95.000 mensual",
            vendedor="Inmobiliaria Ejemplo",
            tipo_vendedor="Inmobiliaria",
            scrape_exitoso=True,
            errores=[]
        ),
        "sample_providencia": ScrapedProperty(
            url="https://departamento.mercadolibre.cl/sample-providencia",
            meli_id="SAMPLE001",
            titulo="Moderno Depto en Providencia, Metro Los Leones",
            precio_valor=4500.0,
            precio_moneda=Currency.UF,
            precio_texto_original="4.500 UF",
            comuna="Providencia",
            region="Región Metropolitana",
            direccion="Providencia, cerca Metro Los Leones",
            superficie_util=55.0,
            habitaciones=1,
            banos=1,
            estacionamientos=1,
            gastos_comunes=70000.0,
            gastos_comunes_texto="$70.000 mensual",
            scrape_exitoso=True,
            errores=[]
        ),
        "sample_nunoa": ScrapedProperty(
            url="https://departamento.mercadolibre.cl/sample-nunoa",
            meli_id="SAMPLE002",
            titulo="Departamento Amplio en Ñuñoa, 3D 2B",
            precio_valor=6200.0,
            precio_moneda=Currency.UF,
            precio_texto_original="6.200 UF",
            comuna="Ñuñoa",
            region="Región Metropolitana",
            direccion="Ñuñoa, Av. Irarrázaval",
            superficie_util=85.0,
            superficie_total=95.0,
            habitaciones=3,
            banos=2,
            estacionamientos=2,
            bodegas=1,
            gastos_comunes=110000.0,
            gastos_comunes_texto="$110.000 mensual",
            scrape_exitoso=True,
            errores=[]
        ),
    }

    return samples.get(sample_id, samples["MLC2685598554"])


# =============================================================================
# EJEMPLO DE USO
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("MercadoLibre Chile Property Scraper")
    print("=" * 60)

    # URL de ejemplo
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = "https://departamento.mercadolibre.cl/MLC-2685598554"

    print(f"\nURL: {url}")
    print("-" * 60)

    # Intentar scraping real
    print("\nIntentando scraping...")
    result = scrape_with_fallback(url, try_playwright=True)

    # Si falló, usar datos de ejemplo
    if not result.scrape_exitoso:
        print("\n⚠️  Scraping no disponible, usando datos de ejemplo...")
        result = get_sample_property("MLC2685598554")

    # Mostrar resultados
    print("\n--- RESULTADOS ---")

    if result.scrape_exitoso:
        print(f"✓ Datos obtenidos exitosamente")
    else:
        print(f"✗ Errores en obtención de datos:")
        for err in result.errores:
            print(f"  - {err}")

    print(f"\nTítulo: {result.titulo}")
    print(f"Precio: {result.precio_texto_original}")
    print(f"  - Valor: {result.precio_valor}")
    print(f"  - Moneda: {result.precio_moneda.value}")

    print(f"\nUbicación:")
    print(f"  - Comuna: {result.comuna}")
    print(f"  - Región: {result.region}")
    print(f"  - Dirección: {result.direccion}")

    print(f"\nCaracterísticas:")
    print(f"  - Superficie útil: {result.superficie_util} m²")
    print(f"  - Superficie total: {result.superficie_total} m²")
    print(f"  - Habitaciones: {result.habitaciones}")
    print(f"  - Baños: {result.banos}")
    print(f"  - Estacionamientos: {result.estacionamientos}")

    print(f"\nGastos:")
    print(f"  - Gastos comunes: {result.gastos_comunes} CLP")

    print(f"\nVendedor: {result.vendedor}")

    print("\n" + "=" * 60)

    # Mostrar cómo convertir a PropertyInput
    print("\n--- CONVERSIÓN A PROPERTY INPUT ---")
    print("Para usar con el motor financiero:")
    print(f"""
from financials import PropertyInput

property_input = PropertyInput(
    precio_uf={result.precio_valor},
    arriendo_clp=850000,  # Estimación para {result.comuna}
    gastos_comunes_clp={result.gastos_comunes or 80000},
    superficie_m2={result.superficie_util or 65},
    comuna="{result.comuna}"
)
""")
