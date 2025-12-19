"""
Motor Financiero Core para Inversiones Inmobiliarias en Chile
============================================================

Este módulo implementa toda la lógica de cálculo financiero para evaluar
la rentabilidad de propiedades en Chile para inversionistas extranjeros.

Monedas:
- UF (Unidad de Fomento): Indexada a inflación, usada para precios y créditos
- CLP (Peso Chileno): Arriendos y gastos operativos
- EUR (Euro): Moneda base del inversionista para outputs finales

Autor: Dashboard MVP Chile Real Estate
Versión: 1.0.0
"""

import requests
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from functools import lru_cache
import numpy_financial as npf
import numpy as np


# =============================================================================
# CONSTANTES DEL MERCADO CHILENO
# =============================================================================

# Gastos operacionales fijos en UF (estándar del mercado)
FIXED_COSTS_UF = {
    "tasacion": 3.0,           # Tasación de la propiedad
    "estudio_titulos": 5.0,    # Estudio de títulos legales
    "borrador_escritura": 3.0, # Borrador de escritura pública
    "notaria": 4.0,            # Gastos notariales
}

# Tasas y porcentajes del mercado chileno
MARKET_RATES = {
    "impuesto_mutuo": 0.008,       # 0.8% del monto del crédito
    "cbrs_rate": 0.005,            # 0.5% Conservador de Bienes Raíces
    "cbrs_tope_uf": 50.0,          # Tope máximo CBRS en UF
    "corretaje_rate": 0.02,        # 2% comisión corretaje
    "iva": 0.19,                   # IVA Chile 19%
    "contribuciones_annual": 0.0075,  # 0.75% del valor comercial anual
    "desgravamen_monthly": 0.00025,   # 0.025% del saldo mensual
    "incendio_sismo_monthly": 0.0002, # 0.02% del valor asegurado mensual
    "default_pie": 0.30,           # 30% pie para no residentes
    "default_property_mgmt": 0.10, # 10% administración
    "default_maintenance": 0.05,   # 5% mantención
    "default_vacancy": 0.05,       # 5% vacancia anual
    "default_plusvalia": 0.02,     # 2% plusvalía anual
}


# =============================================================================
# ESTRUCTURAS DE DATOS (DATACLASSES)
# =============================================================================

@dataclass
class CurrencyRates:
    """Valores de monedas del día desde mindicador.cl"""
    uf_clp: float          # Valor UF en CLP
    eur_clp: float         # Valor EUR en CLP
    usd_clp: float         # Valor USD en CLP (referencia)
    fecha: datetime

    @property
    def uf_eur(self) -> float:
        """UF expresada en EUR"""
        return self.uf_clp / self.eur_clp

    @property
    def clp_eur(self) -> float:
        """CLP expresado en EUR"""
        return 1 / self.eur_clp


@dataclass
class PropertyInput:
    """Datos de entrada de la propiedad"""
    precio_uf: float                          # Precio de venta en UF
    arriendo_clp: float                       # Arriendo mensual esperado en CLP
    gastos_comunes_clp: float = 0.0           # Gastos comunes mensuales en CLP
    superficie_m2: float = 0.0                # Superficie útil
    comuna: str = ""                          # Ubicación
    url: str = ""                             # URL de origen


@dataclass
class MortgageInput:
    """Parámetros del crédito hipotecario"""
    pie_percent: float = 0.30                 # Porcentaje de pie (default 30%)
    tasa_anual: float = 4.5                   # Tasa anual en % (ej: 4.5 = UF + 4.5%)
    plazo_anos: int = 20                      # Plazo en años


@dataclass
class OperatingInput:
    """Parámetros operativos configurables"""
    vacancy_rate: float = 0.05               # Tasa de vacancia anual
    property_mgmt_rate: float = 0.10         # Tasa de administración
    maintenance_rate: float = 0.05           # Tasa de mantención
    plusvalia_annual: float = 0.02           # Plusvalía anual esperada


@dataclass
class CapexBreakdown:
    """Desglose detallado del CAPEX (Inversión Inicial)"""
    pie_uf: float                            # Pie en UF
    impuesto_mutuo_uf: float                 # Impuesto al mutuo
    tasacion_uf: float                       # Costo tasación
    estudio_titulos_uf: float                # Estudio de títulos
    borrador_escritura_uf: float             # Borrador escritura
    notaria_uf: float                        # Gastos notariales
    cbrs_uf: float                           # Conservador Bienes Raíces
    corretaje_uf: float                      # Comisión corretaje (con IVA)

    @property
    def total_uf(self) -> float:
        """Total CAPEX en UF"""
        return (
            self.pie_uf +
            self.impuesto_mutuo_uf +
            self.tasacion_uf +
            self.estudio_titulos_uf +
            self.borrador_escritura_uf +
            self.notaria_uf +
            self.cbrs_uf +
            self.corretaje_uf
        )

    @property
    def gastos_cierre_uf(self) -> float:
        """Solo gastos de cierre (sin pie)"""
        return self.total_uf - self.pie_uf

    def to_dict(self) -> Dict[str, float]:
        """Convertir a diccionario para visualización"""
        return {
            "Pie (Down Payment)": self.pie_uf,
            "Impuesto al Mutuo": self.impuesto_mutuo_uf,
            "Tasación": self.tasacion_uf,
            "Estudio de Títulos": self.estudio_titulos_uf,
            "Borrador Escritura": self.borrador_escritura_uf,
            "Notaría": self.notaria_uf,
            "Conservador (CBRS)": self.cbrs_uf,
            "Corretaje (+ IVA)": self.corretaje_uf,
            "TOTAL": self.total_uf,
        }


@dataclass
class MortgagePayment:
    """Detalle del dividendo hipotecario mensual"""
    cuota_base_uf: float                     # Cuota base (capital + interés)
    seguro_desgravamen_uf: float             # Seguro de desgravamen
    seguro_incendio_uf: float                # Seguro incendio/sismo

    @property
    def dividendo_total_uf(self) -> float:
        """Dividendo total mensual en UF"""
        return self.cuota_base_uf + self.seguro_desgravamen_uf + self.seguro_incendio_uf


@dataclass
class OpexBreakdown:
    """Desglose de gastos operativos mensuales"""
    contribuciones_clp: float                # Contribuciones (impuesto territorial)
    administracion_clp: float                # Property management
    mantencion_clp: float                    # Reserva mantención
    vacancia_clp: float                      # Provisión vacancia
    gastos_comunes_clp: float                # Gastos comunes del edificio

    @property
    def total_clp(self) -> float:
        """Total OPEX mensual en CLP"""
        return (
            self.contribuciones_clp +
            self.administracion_clp +
            self.mantencion_clp +
            self.vacancia_clp +
            self.gastos_comunes_clp
        )

    def to_dict(self) -> Dict[str, float]:
        """Convertir a diccionario para visualización"""
        return {
            "Contribuciones": self.contribuciones_clp,
            "Administración": self.administracion_clp,
            "Mantención": self.mantencion_clp,
            "Vacancia": self.vacancia_clp,
            "Gastos Comunes": self.gastos_comunes_clp,
            "TOTAL": self.total_clp,
        }


@dataclass
class InvestmentMetrics:
    """Métricas de retorno de la inversión"""
    # Valores absolutos
    precio_total_uf: float
    precio_total_eur: float
    inversion_inicial_uf: float              # CAPEX total
    inversion_inicial_eur: float
    dividendo_mensual_uf: float
    dividendo_mensual_eur: float

    # Flujo de caja
    noi_mensual_clp: float                   # Net Operating Income
    noi_mensual_eur: float
    cashflow_mensual_clp: float              # Después de dividendo
    cashflow_mensual_eur: float

    # Métricas de retorno
    cap_rate: float                          # NOI anual / Precio propiedad
    cash_on_cash: float                      # Cashflow anual / Cash invertido
    irr_5_years: Optional[float]             # TIR a 5 años
    irr_10_years: Optional[float]            # TIR a 10 años

    # Desgloses
    capex_breakdown: CapexBreakdown
    opex_breakdown: OpexBreakdown
    mortgage_payment: MortgagePayment

    # Metadata
    currency_rates: CurrencyRates
    is_cashflow_positive: bool


# =============================================================================
# API DE INDICADORES ECONÓMICOS
# =============================================================================

class CurrencyAPI:
    """
    Cliente para la API de mindicador.cl

    Provee valores diarios de:
    - UF (Unidad de Fomento)
    - Euro
    - Dólar

    Implementa caching simple para evitar llamadas repetidas.
    """

    BASE_URL = "https://mindicador.cl/api"
    CACHE_DURATION = timedelta(hours=1)  # Cache por 1 hora

    _cache: Dict[str, Tuple[Any, datetime]] = {}

    @classmethod
    def _get_cached(cls, key: str) -> Optional[Any]:
        """Obtener valor del cache si no ha expirado"""
        if key in cls._cache:
            value, timestamp = cls._cache[key]
            if datetime.now() - timestamp < cls.CACHE_DURATION:
                return value
        return None

    @classmethod
    def _set_cache(cls, key: str, value: Any) -> None:
        """Guardar valor en cache"""
        cls._cache[key] = (value, datetime.now())

    @classmethod
    def fetch_rates(cls, use_cache: bool = True) -> CurrencyRates:
        """
        Obtener tasas de cambio del día.

        Returns:
            CurrencyRates con valores actuales de UF, EUR, USD

        Raises:
            ConnectionError: Si no se puede conectar a la API
            ValueError: Si la respuesta es inválida
        """
        cache_key = "rates_today"

        if use_cache:
            cached = cls._get_cached(cache_key)
            if cached:
                return cached

        try:
            response = requests.get(cls.BASE_URL, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Extraer valores
            uf_value = data.get("uf", {}).get("valor")
            euro_value = data.get("euro", {}).get("valor")
            dolar_value = data.get("dolar", {}).get("valor")

            if not all([uf_value, euro_value, dolar_value]):
                raise ValueError("Respuesta incompleta de la API")

            rates = CurrencyRates(
                uf_clp=float(uf_value),
                eur_clp=float(euro_value),
                usd_clp=float(dolar_value),
                fecha=datetime.now()
            )

            cls._set_cache(cache_key, rates)
            return rates

        except requests.RequestException as e:
            raise ConnectionError(f"Error conectando a mindicador.cl: {e}")
        except (KeyError, TypeError) as e:
            raise ValueError(f"Error parseando respuesta de API: {e}")

    @classmethod
    def get_historical_uf(cls, fecha: datetime) -> float:
        """
        Obtener valor histórico de UF para una fecha específica.

        Útil para cálculos de proyección y backtesting.
        """
        fecha_str = fecha.strftime("%d-%m-%Y")
        url = f"{cls.BASE_URL}/uf/{fecha_str}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "serie" in data and len(data["serie"]) > 0:
                return float(data["serie"][0]["valor"])
            raise ValueError("No hay datos para esa fecha")

        except requests.RequestException as e:
            raise ConnectionError(f"Error obteniendo UF histórica: {e}")


# =============================================================================
# CALCULADORA PRINCIPAL
# =============================================================================

class RealEstateCalculator:
    """
    Calculadora de inversiones inmobiliarias para Chile.

    Implementa toda la lógica financiera:
    - Cálculo de CAPEX (inversión inicial con todos los costos de cierre)
    - Amortización francesa para crédito hipotecario
    - OPEX mensual (contribuciones, administración, mantención, vacancia)
    - Métricas de retorno (Cap Rate, Cash-on-Cash, TIR)

    Usage:
        rates = CurrencyAPI.fetch_rates()
        calc = RealEstateCalculator(rates)

        property_data = PropertyInput(precio_uf=5000, arriendo_clp=800000)
        mortgage = MortgageInput(pie_percent=0.30, tasa_anual=4.5, plazo_anos=20)
        operating = OperatingInput()

        metrics = calc.analyze_investment(property_data, mortgage, operating)
    """

    def __init__(self, rates: CurrencyRates):
        """
        Inicializar calculadora con tasas de cambio del día.

        Args:
            rates: CurrencyRates con valores actuales de UF, EUR, USD
        """
        self.rates = rates

    # -------------------------------------------------------------------------
    # CONVERSIONES DE MONEDA
    # -------------------------------------------------------------------------

    def uf_to_clp(self, amount_uf: float) -> float:
        """Convertir UF a CLP"""
        return amount_uf * self.rates.uf_clp

    def clp_to_uf(self, amount_clp: float) -> float:
        """Convertir CLP a UF"""
        return amount_clp / self.rates.uf_clp

    def uf_to_eur(self, amount_uf: float) -> float:
        """Convertir UF a EUR"""
        clp = self.uf_to_clp(amount_uf)
        return clp / self.rates.eur_clp

    def clp_to_eur(self, amount_clp: float) -> float:
        """Convertir CLP a EUR"""
        return amount_clp / self.rates.eur_clp

    def eur_to_clp(self, amount_eur: float) -> float:
        """Convertir EUR a CLP"""
        return amount_eur * self.rates.eur_clp

    def eur_to_uf(self, amount_eur: float) -> float:
        """Convertir EUR a UF"""
        clp = self.eur_to_clp(amount_eur)
        return self.clp_to_uf(clp)

    # -------------------------------------------------------------------------
    # CÁLCULO DE CRÉDITO HIPOTECARIO
    # -------------------------------------------------------------------------

    def calculate_mortgage_payment(
        self,
        principal_uf: float,
        rate_annual: float,
        years: int,
        property_value_uf: float
    ) -> MortgagePayment:
        """
        Calcular dividendo mensual usando amortización francesa.

        La fórmula de amortización francesa es:

            PMT = P * [r(1+r)^n] / [(1+r)^n - 1]

        Donde:
            P = Principal (monto del crédito)
            r = Tasa de interés mensual (tasa_anual / 12 / 100)
            n = Número total de cuotas (años * 12)

        Args:
            principal_uf: Monto del crédito en UF
            rate_annual: Tasa anual en % (ej: 4.5 significa UF + 4.5%)
            years: Plazo en años
            property_value_uf: Valor de la propiedad (para seguros)

        Returns:
            MortgagePayment con desglose de cuota base y seguros
        """
        # Tasa mensual: convertir % anual a decimal mensual
        # Ej: 4.5% anual -> 0.045/12 = 0.00375 mensual
        monthly_rate = (rate_annual / 100) / 12

        # Número total de cuotas
        n_payments = years * 12

        # Cálculo de cuota usando numpy_financial
        # pmt devuelve valor negativo (egreso), por eso usamos -pmt
        cuota_base = -npf.pmt(monthly_rate, n_payments, principal_uf)

        # Seguros obligatorios (calculados sobre saldo inicial para simplificar)
        # En la práctica el desgravamen baja con el saldo, pero para MVP usamos promedio
        seguro_desgravamen = principal_uf * MARKET_RATES["desgravamen_monthly"]

        # Seguro incendio/sismo sobre valor de la propiedad
        seguro_incendio = property_value_uf * MARKET_RATES["incendio_sismo_monthly"]

        return MortgagePayment(
            cuota_base_uf=round(cuota_base, 4),
            seguro_desgravamen_uf=round(seguro_desgravamen, 4),
            seguro_incendio_uf=round(seguro_incendio, 4)
        )

    def generate_amortization_schedule(
        self,
        principal_uf: float,
        rate_annual: float,
        years: int
    ) -> List[Dict[str, float]]:
        """
        Generar tabla de amortización completa.

        Útil para proyecciones y gráficos de equity acumulado.

        Returns:
            Lista de diccionarios con: periodo, cuota, interes, capital, saldo
        """
        monthly_rate = (rate_annual / 100) / 12
        n_payments = years * 12
        cuota = -npf.pmt(monthly_rate, n_payments, principal_uf)

        schedule = []
        saldo = principal_uf

        for periodo in range(1, n_payments + 1):
            interes = saldo * monthly_rate
            capital = cuota - interes
            saldo -= capital

            schedule.append({
                "periodo": periodo,
                "cuota_uf": round(cuota, 4),
                "interes_uf": round(interes, 4),
                "capital_uf": round(capital, 4),
                "saldo_uf": round(max(0, saldo), 4)
            })

        return schedule

    # -------------------------------------------------------------------------
    # CÁLCULO DE INVERSIÓN INICIAL (CAPEX)
    # -------------------------------------------------------------------------

    def calculate_initial_investment(
        self,
        property_value_uf: float,
        pie_percent: float
    ) -> CapexBreakdown:
        """
        Calcular inversión inicial total incluyendo todos los costos de cierre.

        El CAPEX incluye:
        1. Pie (Down Payment): % del valor de la propiedad
        2. Impuesto al Mutuo: 0.8% del monto del crédito
        3. Gastos Fijos: Tasación, Estudio Títulos, Borrador, Notaría
        4. CBRS: 0.5% del valor (con tope de 50 UF)
        5. Corretaje: 2% + IVA del valor de venta

        Args:
            property_value_uf: Valor de la propiedad en UF
            pie_percent: Porcentaje de pie (0.30 = 30%)

        Returns:
            CapexBreakdown con desglose detallado
        """
        # 1. Pie (Down Payment)
        pie_uf = property_value_uf * pie_percent

        # 2. Monto del crédito
        credito_uf = property_value_uf - pie_uf

        # 3. Impuesto al Mutuo (0.8% del crédito)
        impuesto_mutuo = credito_uf * MARKET_RATES["impuesto_mutuo"]

        # 4. Gastos fijos en UF
        tasacion = FIXED_COSTS_UF["tasacion"]
        estudio_titulos = FIXED_COSTS_UF["estudio_titulos"]
        borrador_escritura = FIXED_COSTS_UF["borrador_escritura"]
        notaria = FIXED_COSTS_UF["notaria"]

        # 5. CBRS: 0.5% con tope
        cbrs = min(
            property_value_uf * MARKET_RATES["cbrs_rate"],
            MARKET_RATES["cbrs_tope_uf"]
        )

        # 6. Corretaje: 2% + IVA (19%)
        corretaje_neto = property_value_uf * MARKET_RATES["corretaje_rate"]
        corretaje_con_iva = corretaje_neto * (1 + MARKET_RATES["iva"])

        return CapexBreakdown(
            pie_uf=round(pie_uf, 2),
            impuesto_mutuo_uf=round(impuesto_mutuo, 2),
            tasacion_uf=tasacion,
            estudio_titulos_uf=estudio_titulos,
            borrador_escritura_uf=borrador_escritura,
            notaria_uf=notaria,
            cbrs_uf=round(cbrs, 2),
            corretaje_uf=round(corretaje_con_iva, 2)
        )

    # -------------------------------------------------------------------------
    # CÁLCULO DE GASTOS OPERATIVOS (OPEX)
    # -------------------------------------------------------------------------

    def calculate_monthly_opex(
        self,
        property_value_uf: float,
        arriendo_clp: float,
        gastos_comunes_clp: float,
        operating: OperatingInput
    ) -> OpexBreakdown:
        """
        Calcular gastos operativos mensuales.

        El OPEX incluye:
        1. Contribuciones: ~0.75% anual del valor comercial (mensualizado)
        2. Administración: 10% + IVA del arriendo
        3. Mantención: 5% del arriendo (reserva)
        4. Vacancia: % del arriendo (provisión)
        5. Gastos Comunes: Del edificio/condominio

        Args:
            property_value_uf: Valor de la propiedad
            arriendo_clp: Arriendo mensual en CLP
            gastos_comunes_clp: Gastos comunes mensuales
            operating: Parámetros operativos configurables

        Returns:
            OpexBreakdown con desglose detallado
        """
        # 1. Contribuciones (impuesto territorial)
        # 0.75% anual del valor comercial, dividido en 12
        valor_comercial_clp = self.uf_to_clp(property_value_uf)
        contribuciones_annual = valor_comercial_clp * MARKET_RATES["contribuciones_annual"]
        contribuciones_monthly = contribuciones_annual / 12

        # 2. Administración (Property Management): % del arriendo + IVA
        admin_neto = arriendo_clp * operating.property_mgmt_rate
        administracion = admin_neto * (1 + MARKET_RATES["iva"])

        # 3. Mantención/Reparaciones: % del arriendo
        mantencion = arriendo_clp * operating.maintenance_rate

        # 4. Vacancia: % anual del arriendo mensualizado
        vacancia = arriendo_clp * operating.vacancy_rate

        return OpexBreakdown(
            contribuciones_clp=round(contribuciones_monthly, 0),
            administracion_clp=round(administracion, 0),
            mantencion_clp=round(mantencion, 0),
            vacancia_clp=round(vacancia, 0),
            gastos_comunes_clp=round(gastos_comunes_clp, 0)
        )

    # -------------------------------------------------------------------------
    # CÁLCULO DE FLUJO DE CAJA (CASHFLOW)
    # -------------------------------------------------------------------------

    def calculate_monthly_cashflow(
        self,
        arriendo_clp: float,
        opex: OpexBreakdown,
        mortgage: MortgagePayment
    ) -> Tuple[float, float]:
        """
        Calcular flujo de caja mensual.

        Fórmula:
            NOI = Arriendo - OPEX (sin dividendo)
            Cashflow = NOI - Dividendo

        Args:
            arriendo_clp: Ingreso por arriendo
            opex: Gastos operativos
            mortgage: Pago hipotecario

        Returns:
            Tuple de (NOI en CLP, Cashflow en CLP)
        """
        # NOI (Net Operating Income) = Ingresos - Gastos Operativos
        noi_clp = arriendo_clp - opex.total_clp

        # Convertir dividendo de UF a CLP
        dividendo_clp = self.uf_to_clp(mortgage.dividendo_total_uf)

        # Cashflow = NOI - Dividendo
        cashflow_clp = noi_clp - dividendo_clp

        return noi_clp, cashflow_clp

    # -------------------------------------------------------------------------
    # MÉTRICAS DE RETORNO
    # -------------------------------------------------------------------------

    def calculate_cap_rate(
        self,
        noi_annual_clp: float,
        property_value_clp: float
    ) -> float:
        """
        Calcular Cap Rate (Tasa de Capitalización).

        Fórmula:
            Cap Rate = NOI Anual / Valor de la Propiedad

        El Cap Rate mide el retorno "sin apalancamiento", es decir,
        como si hubieras pagado la propiedad completa en efectivo.

        Típicamente:
        - 3-4%: Mercado caro / baja rentabilidad
        - 5-6%: Mercado equilibrado
        - 7%+: Alta rentabilidad / mayor riesgo

        Returns:
            Cap Rate como decimal (ej: 0.055 = 5.5%)
        """
        if property_value_clp <= 0:
            return 0.0
        return noi_annual_clp / property_value_clp

    def calculate_cash_on_cash(
        self,
        cashflow_annual_clp: float,
        cash_invested_clp: float
    ) -> float:
        """
        Calcular Cash-on-Cash Return.

        Fórmula:
            CoC = Cashflow Anual / Cash Invertido (CAPEX)

        El CoC mide el retorno sobre el dinero efectivamente invertido,
        considerando el apalancamiento del crédito.

        Puede ser negativo si el cashflow es negativo.

        Returns:
            Cash-on-Cash como decimal (ej: 0.08 = 8%)
        """
        if cash_invested_clp <= 0:
            return 0.0
        return cashflow_annual_clp / cash_invested_clp

    def calculate_irr(
        self,
        cash_invested: float,
        monthly_cashflows: List[float],
        exit_value: float
    ) -> Optional[float]:
        """
        Calcular TIR (Tasa Interna de Retorno).

        La TIR es la tasa de descuento que hace que el VPN = 0.

        Args:
            cash_invested: Inversión inicial (negativo en el flujo)
            monthly_cashflows: Lista de cashflows mensuales
            exit_value: Valor de venta al final (equity)

        Returns:
            TIR anualizada como decimal, o None si no converge
        """
        # Construir flujo de caja
        # Periodo 0: inversión inicial (negativo)
        # Periodos 1-n: cashflows mensuales
        # Periodo final: incluye valor de salida

        cashflows = [-cash_invested] + monthly_cashflows[:-1]
        cashflows.append(monthly_cashflows[-1] + exit_value)

        try:
            # IRR mensual
            irr_monthly = npf.irr(cashflows)

            if irr_monthly is None or np.isnan(irr_monthly):
                return None

            # Convertir a anual: (1 + r_monthly)^12 - 1
            irr_annual = (1 + irr_monthly) ** 12 - 1
            return irr_annual

        except Exception:
            return None

    # -------------------------------------------------------------------------
    # PROYECCIONES
    # -------------------------------------------------------------------------

    def project_property_value(
        self,
        initial_value_uf: float,
        years: int,
        plusvalia_rate: float
    ) -> List[float]:
        """
        Proyectar valor de la propiedad con plusvalía.

        Args:
            initial_value_uf: Valor inicial
            years: Años a proyectar
            plusvalia_rate: Tasa anual de apreciación

        Returns:
            Lista de valores por año
        """
        values = [initial_value_uf]
        for _ in range(years):
            values.append(values[-1] * (1 + plusvalia_rate))
        return values

    def project_equity(
        self,
        property_values: List[float],
        amortization_schedule: List[Dict[str, float]]
    ) -> List[Dict[str, float]]:
        """
        Proyectar equity acumulado año por año.

        Equity = Valor Propiedad - Saldo Deuda

        Returns:
            Lista de diccionarios con año, valor, deuda, equity
        """
        projections = []

        for year in range(len(property_values)):
            property_value = property_values[year]

            # Obtener saldo de deuda al final del año
            if year == 0:
                # Año 0: saldo inicial
                debt = amortization_schedule[0]["saldo_uf"] if amortization_schedule else 0
            else:
                # Fin del año = mes 12 * año
                month_index = min(year * 12 - 1, len(amortization_schedule) - 1)
                debt = amortization_schedule[month_index]["saldo_uf"]

            equity = property_value - debt

            projections.append({
                "year": year,
                "property_value_uf": round(property_value, 2),
                "debt_uf": round(debt, 2),
                "equity_uf": round(equity, 2)
            })

        return projections

    # -------------------------------------------------------------------------
    # ANÁLISIS COMPLETO
    # -------------------------------------------------------------------------

    def analyze_investment(
        self,
        property_input: PropertyInput,
        mortgage_input: MortgageInput,
        operating_input: OperatingInput
    ) -> InvestmentMetrics:
        """
        Realizar análisis completo de la inversión.

        Este método orquesta todos los cálculos y devuelve
        un objeto InvestmentMetrics con todas las métricas.

        Args:
            property_input: Datos de la propiedad
            mortgage_input: Parámetros del crédito
            operating_input: Parámetros operativos

        Returns:
            InvestmentMetrics con análisis completo
        """
        precio_uf = property_input.precio_uf
        arriendo_clp = property_input.arriendo_clp
        gastos_comunes = property_input.gastos_comunes_clp

        # 1. Calcular CAPEX
        capex = self.calculate_initial_investment(
            property_value_uf=precio_uf,
            pie_percent=mortgage_input.pie_percent
        )

        # 2. Calcular crédito
        credito_uf = precio_uf - capex.pie_uf
        mortgage_payment = self.calculate_mortgage_payment(
            principal_uf=credito_uf,
            rate_annual=mortgage_input.tasa_anual,
            years=mortgage_input.plazo_anos,
            property_value_uf=precio_uf
        )

        # 3. Calcular OPEX
        opex = self.calculate_monthly_opex(
            property_value_uf=precio_uf,
            arriendo_clp=arriendo_clp,
            gastos_comunes_clp=gastos_comunes,
            operating=operating_input
        )

        # 4. Calcular flujo de caja
        noi_clp, cashflow_clp = self.calculate_monthly_cashflow(
            arriendo_clp=arriendo_clp,
            opex=opex,
            mortgage=mortgage_payment
        )

        # 5. Calcular métricas
        precio_clp = self.uf_to_clp(precio_uf)
        capex_clp = self.uf_to_clp(capex.total_uf)

        cap_rate = self.calculate_cap_rate(
            noi_annual_clp=noi_clp * 12,
            property_value_clp=precio_clp
        )

        cash_on_cash = self.calculate_cash_on_cash(
            cashflow_annual_clp=cashflow_clp * 12,
            cash_invested_clp=capex_clp
        )

        # 6. Calcular TIR a 5 y 10 años
        amortization = self.generate_amortization_schedule(
            principal_uf=credito_uf,
            rate_annual=mortgage_input.tasa_anual,
            years=mortgage_input.plazo_anos
        )

        # Proyección de valor
        property_values = self.project_property_value(
            initial_value_uf=precio_uf,
            years=10,
            plusvalia_rate=operating_input.plusvalia_annual
        )

        # TIR 5 años
        cashflows_5y = [cashflow_clp] * 60  # 5 años * 12 meses
        equity_5y = self.uf_to_clp(property_values[5] - amortization[59]["saldo_uf"])
        irr_5 = self.calculate_irr(capex_clp, cashflows_5y, equity_5y)

        # TIR 10 años
        cashflows_10y = [cashflow_clp] * 120  # 10 años * 12 meses
        equity_10y = self.uf_to_clp(property_values[10] - amortization[119]["saldo_uf"])
        irr_10 = self.calculate_irr(capex_clp, cashflows_10y, equity_10y)

        # 7. Conversiones a EUR
        precio_eur = self.uf_to_eur(precio_uf)
        capex_eur = self.uf_to_eur(capex.total_uf)
        dividendo_eur = self.uf_to_eur(mortgage_payment.dividendo_total_uf)
        noi_eur = self.clp_to_eur(noi_clp)
        cashflow_eur = self.clp_to_eur(cashflow_clp)

        return InvestmentMetrics(
            # Valores absolutos
            precio_total_uf=precio_uf,
            precio_total_eur=round(precio_eur, 2),
            inversion_inicial_uf=capex.total_uf,
            inversion_inicial_eur=round(capex_eur, 2),
            dividendo_mensual_uf=mortgage_payment.dividendo_total_uf,
            dividendo_mensual_eur=round(dividendo_eur, 2),

            # Flujo de caja
            noi_mensual_clp=round(noi_clp, 0),
            noi_mensual_eur=round(noi_eur, 2),
            cashflow_mensual_clp=round(cashflow_clp, 0),
            cashflow_mensual_eur=round(cashflow_eur, 2),

            # Métricas de retorno
            cap_rate=round(cap_rate, 4),
            cash_on_cash=round(cash_on_cash, 4),
            irr_5_years=round(irr_5, 4) if irr_5 else None,
            irr_10_years=round(irr_10, 4) if irr_10 else None,

            # Desgloses
            capex_breakdown=capex,
            opex_breakdown=opex,
            mortgage_payment=mortgage_payment,

            # Metadata
            currency_rates=self.rates,
            is_cashflow_positive=cashflow_clp > 0
        )


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

def format_currency(amount: float, currency: str = "CLP", decimals: int = 0) -> str:
    """
    Formatear montos con símbolo de moneda.

    Args:
        amount: Monto a formatear
        currency: CLP, UF, EUR
        decimals: Decimales a mostrar
    """
    symbols = {
        "CLP": "$",
        "UF": "UF ",
        "EUR": "€"
    }
    symbol = symbols.get(currency, "")

    if currency == "CLP":
        return f"{symbol}{amount:,.{decimals}f}".replace(",", ".")
    elif currency == "EUR":
        return f"{symbol}{amount:,.{decimals}f}"
    else:
        return f"{symbol}{amount:,.{decimals}f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Formatear porcentaje"""
    return f"{value * 100:.{decimals}f}%"


# =============================================================================
# EJEMPLO DE USO
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Motor Financiero - Chile Real Estate Investment Calculator")
    print("=" * 60)

    # 1. Obtener tasas de cambio
    print("\n[1] Obteniendo tasas de cambio de mindicador.cl...")
    try:
        rates = CurrencyAPI.fetch_rates()
        print(f"    UF: {format_currency(rates.uf_clp, 'CLP', 2)}")
        print(f"    EUR: {format_currency(rates.eur_clp, 'CLP', 2)}")
        print(f"    USD: {format_currency(rates.usd_clp, 'CLP', 2)}")
    except (ConnectionError, ValueError) as e:
        print(f"    Error: {e}")
        print("    Usando valores de respaldo...")
        rates = CurrencyRates(
            uf_clp=38500.0,  # Valor aproximado
            eur_clp=1020.0,
            usd_clp=980.0,
            fecha=datetime.now()
        )

    # 2. Crear calculadora
    calc = RealEstateCalculator(rates)

    # 3. Definir propiedad de ejemplo
    print("\n[2] Analizando propiedad de ejemplo...")
    print("    - Precio: 5,000 UF")
    print("    - Arriendo: $800,000 CLP/mes")
    print("    - Gastos Comunes: $80,000 CLP/mes")

    property_data = PropertyInput(
        precio_uf=5000,
        arriendo_clp=800000,
        gastos_comunes_clp=80000,
        superficie_m2=65,
        comuna="Providencia"
    )

    mortgage = MortgageInput(
        pie_percent=0.30,
        tasa_anual=4.5,
        plazo_anos=20
    )

    operating = OperatingInput(
        vacancy_rate=0.05,
        property_mgmt_rate=0.10,
        maintenance_rate=0.05,
        plusvalia_annual=0.02
    )

    # 4. Ejecutar análisis
    metrics = calc.analyze_investment(property_data, mortgage, operating)

    # 5. Mostrar resultados
    print("\n" + "=" * 60)
    print("RESULTADOS DEL ANÁLISIS")
    print("=" * 60)

    print("\n--- INVERSIÓN INICIAL (CAPEX) ---")
    for key, value in metrics.capex_breakdown.to_dict().items():
        eur_value = calc.uf_to_eur(value)
        print(f"    {key}: UF {value:,.2f} (€{eur_value:,.2f})")

    print("\n--- DIVIDENDO MENSUAL ---")
    print(f"    Cuota Base: UF {metrics.mortgage_payment.cuota_base_uf:.4f}")
    print(f"    Seg. Desgravamen: UF {metrics.mortgage_payment.seguro_desgravamen_uf:.4f}")
    print(f"    Seg. Incendio: UF {metrics.mortgage_payment.seguro_incendio_uf:.4f}")
    print(f"    TOTAL: UF {metrics.mortgage_payment.dividendo_total_uf:.4f} (€{metrics.dividendo_mensual_eur:.2f})")

    print("\n--- GASTOS OPERATIVOS MENSUALES ---")
    for key, value in metrics.opex_breakdown.to_dict().items():
        eur_value = calc.clp_to_eur(value)
        print(f"    {key}: ${value:,.0f} CLP (€{eur_value:.2f})")

    print("\n--- FLUJO DE CAJA MENSUAL ---")
    print(f"    NOI: ${metrics.noi_mensual_clp:,.0f} CLP (€{metrics.noi_mensual_eur:.2f})")
    print(f"    Cashflow: ${metrics.cashflow_mensual_clp:,.0f} CLP (€{metrics.cashflow_mensual_eur:.2f})")

    if not metrics.is_cashflow_positive:
        print("\n    ⚠️  ADVERTENCIA: Cashflow negativo - requiere inyección de capital")

    print("\n--- MÉTRICAS DE RETORNO ---")
    print(f"    Cap Rate: {format_percentage(metrics.cap_rate)}")
    print(f"    Cash-on-Cash: {format_percentage(metrics.cash_on_cash)}")
    if metrics.irr_5_years:
        print(f"    TIR 5 años: {format_percentage(metrics.irr_5_years)}")
    if metrics.irr_10_years:
        print(f"    TIR 10 años: {format_percentage(metrics.irr_10_years)}")

    print("\n" + "=" * 60)
    print("Análisis completado exitosamente.")
    print("=" * 60)
