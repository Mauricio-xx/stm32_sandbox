"""
Chile Real Estate Investment Dashboard
======================================

Dashboard interactivo para evaluar rentabilidad de propiedades en Chile
para inversionistas extranjeros (especialmente residentes en Alemania).

Ejecutar con: streamlit run app.py

Autor: Dashboard MVP Chile Real Estate
Versión: 1.0.0
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Optional, Dict, Any

# Importar módulos locales
from financials import (
    CurrencyAPI,
    CurrencyRates,
    RealEstateCalculator,
    PropertyInput,
    MortgageInput,
    OperatingInput,
    InvestmentMetrics,
    format_currency,
    format_percentage,
    MARKET_RATES,
)
from scraper import (
    scrape_with_fallback,
    get_sample_property,
    ScrapedProperty,
    Currency,
    create_property_from_scraped,
)
from market_intelligence import (
    MarketIntelligence,
    MarketIntelligenceReport,
    ConnectivityLevel,
    PricePosition,
)


# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Chile Real Estate Investment Calculator",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS personalizado
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .metric-positive {
        color: #28a745;
    }
    .metric-negative {
        color: #dc3545;
    }
    .metric-neutral {
        color: #6c757d;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
    }
    .danger-box {
        background-color: #f8d7da;
        border: 1px solid #dc3545;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #28a745;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
    }
    .stMetric > div {
        background-color: #f8f9fa;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

@st.cache_data(ttl=3600)  # Cache por 1 hora
def get_currency_rates() -> CurrencyRates:
    """Obtener tasas de cambio con cache"""
    try:
        return CurrencyAPI.fetch_rates()
    except Exception:
        # Valores de respaldo
        return CurrencyRates(
            uf_clp=38500.0,
            eur_clp=1020.0,
            usd_clp=980.0,
            fecha=datetime.now()
        )


def format_value(value: float, currency: str, rates: CurrencyRates, calc: RealEstateCalculator) -> str:
    """Formatear valor según moneda seleccionada"""
    if currency == "EUR":
        return f"€{value:,.2f}"
    elif currency == "UF":
        # Convertir de EUR a UF
        uf_value = calc.eur_to_uf(value) if value else 0
        return f"UF {uf_value:,.2f}"
    else:  # CLP
        clp_value = calc.eur_to_clp(value) if value else 0
        return f"${clp_value:,.0f}"


def create_metric_card(title: str, value: str, delta: Optional[str] = None, delta_color: str = "normal"):
    """Crear tarjeta de métrica personalizada"""
    st.metric(label=title, value=value, delta=delta, delta_color=delta_color)


# =============================================================================
# SIDEBAR - INPUTS
# =============================================================================

def render_sidebar(rates: CurrencyRates) -> Dict[str, Any]:
    """Renderizar sidebar con todos los inputs"""

    st.sidebar.title("🏠 Configuración")

    # Sección: Fuente de datos
    st.sidebar.header("📊 Datos de Propiedad")

    data_source = st.sidebar.radio(
        "Fuente de datos:",
        ["URL de MercadoLibre", "Entrada Manual", "Datos de Ejemplo"],
        index=2,  # Default: Datos de ejemplo
        help="Selecciona cómo ingresar los datos de la propiedad"
    )

    scraped_data = None
    property_data = {}

    if data_source == "URL de MercadoLibre":
        url = st.sidebar.text_input(
            "URL de MercadoLibre Chile:",
            placeholder="https://departamento.mercadolibre.cl/MLC-...",
            help="Pega la URL completa del listado"
        )

        if url:
            with st.sidebar.status("Obteniendo datos...", expanded=True):
                scraped_data = scrape_with_fallback(url, try_playwright=False)

                if scraped_data.scrape_exitoso:
                    st.success(f"✓ Datos obtenidos: {scraped_data.titulo[:50]}...")
                    property_data["precio_uf"] = scraped_data.precio_valor or 5000
                    property_data["superficie"] = scraped_data.superficie_util or 65
                    property_data["comuna"] = scraped_data.comuna or "Santiago"
                    property_data["gastos_comunes"] = scraped_data.gastos_comunes or 80000
                else:
                    st.warning("⚠️ No se pudo obtener datos. Use entrada manual.")

    elif data_source == "Datos de Ejemplo":
        sample_options = {
            "Las Condes (5,800 UF)": "MLC2685598554",
            "Providencia (4,500 UF)": "sample_providencia",
            "Ñuñoa (6,200 UF)": "sample_nunoa",
        }
        selected_sample = st.sidebar.selectbox(
            "Seleccionar ejemplo:",
            options=list(sample_options.keys())
        )
        sample_id = sample_options[selected_sample]
        scraped_data = get_sample_property(sample_id)
        property_data["precio_uf"] = scraped_data.precio_valor
        property_data["superficie"] = scraped_data.superficie_util or 65
        property_data["comuna"] = scraped_data.comuna
        property_data["gastos_comunes"] = scraped_data.gastos_comunes or 80000

    # Inputs de propiedad (editables)
    st.sidebar.subheader("Datos de la Propiedad")

    precio_uf = st.sidebar.number_input(
        "Precio (UF):",
        min_value=1000.0,
        max_value=50000.0,
        value=float(property_data.get("precio_uf", 5800.0)),
        step=100.0,
        help="Precio de venta de la propiedad en UF"
    )

    arriendo_clp = st.sidebar.number_input(
        "Arriendo Estimado (CLP/mes):",
        min_value=200000,
        max_value=5000000,
        value=850000,
        step=50000,
        help="Arriendo mensual esperado. Investiga arriendos similares en la zona."
    )

    gastos_comunes = st.sidebar.number_input(
        "Gastos Comunes (CLP/mes):",
        min_value=0,
        max_value=500000,
        value=int(property_data.get("gastos_comunes", 95000)),
        step=5000,
        help="Gastos de administración del edificio"
    )

    superficie = st.sidebar.number_input(
        "Superficie (m²):",
        min_value=20.0,
        max_value=500.0,
        value=float(property_data.get("superficie", 72.0)),
        step=1.0,
    )

    comuna = st.sidebar.text_input(
        "Comuna:",
        value=property_data.get("comuna", "Las Condes")
    )

    # Sección: Financiamiento
    st.sidebar.header("💰 Financiamiento")

    pie_percent = st.sidebar.slider(
        "Pie (Down Payment):",
        min_value=10,
        max_value=100,
        value=30,
        step=5,
        format="%d%%",
        help="Porcentaje del precio a pagar de contado. 30% es estándar para no residentes."
    ) / 100

    tasa_anual = st.sidebar.slider(
        "Tasa de Interés Anual:",
        min_value=2.0,
        max_value=8.0,
        value=4.5,
        step=0.1,
        format="%.1f%%",
        help="Tasa hipotecaria en UF + X%. Las tasas actuales rondan 4-5%."
    )

    plazo_anos = st.sidebar.slider(
        "Plazo del Crédito:",
        min_value=10,
        max_value=30,
        value=20,
        step=1,
        format="%d años"
    )

    # Sección: Parámetros Operativos
    st.sidebar.header("⚙️ Parámetros Operativos")

    vacancy_rate = st.sidebar.slider(
        "Vacancia Estimada:",
        min_value=0,
        max_value=20,
        value=5,
        step=1,
        format="%d%%",
        help="Porcentaje del año que la propiedad podría estar vacía"
    ) / 100

    property_mgmt_rate = st.sidebar.slider(
        "Administración (Property Mgmt):",
        min_value=0,
        max_value=20,
        value=10,
        step=1,
        format="%d%%",
        help="Costo de gestión remota del arriendo"
    ) / 100

    maintenance_rate = st.sidebar.slider(
        "Reserva Mantención:",
        min_value=0,
        max_value=15,
        value=5,
        step=1,
        format="%d%%",
        help="Reserva para reparaciones y mantención"
    ) / 100

    plusvalia_rate = st.sidebar.slider(
        "Plusvalía Anual Esperada:",
        min_value=0.0,
        max_value=6.0,
        value=2.0,
        step=0.5,
        format="%.1f%%",
        help="Apreciación anual esperada de la propiedad"
    ) / 100

    # Sección: Visualización
    st.sidebar.header("👁️ Visualización")

    display_currency = st.sidebar.radio(
        "Moneda de Visualización:",
        ["EUR", "UF", "CLP"],
        index=0,
        help="Selecciona la moneda para ver los resultados"
    )

    projection_years = st.sidebar.slider(
        "Años de Proyección:",
        min_value=5,
        max_value=30,
        value=10,
        step=1
    )

    # Tasas de cambio actuales
    st.sidebar.header("📈 Tasas de Cambio")
    st.sidebar.info(f"""
    **UF:** ${rates.uf_clp:,.2f} CLP
    **EUR:** ${rates.eur_clp:,.2f} CLP
    **USD:** ${rates.usd_clp:,.2f} CLP

    _Actualizado: {rates.fecha.strftime('%Y-%m-%d %H:%M')}_
    """)

    return {
        "property_input": PropertyInput(
            precio_uf=precio_uf,
            arriendo_clp=arriendo_clp,
            gastos_comunes_clp=gastos_comunes,
            superficie_m2=superficie,
            comuna=comuna,
        ),
        "mortgage_input": MortgageInput(
            pie_percent=pie_percent,
            tasa_anual=tasa_anual,
            plazo_anos=plazo_anos,
        ),
        "operating_input": OperatingInput(
            vacancy_rate=vacancy_rate,
            property_mgmt_rate=property_mgmt_rate,
            maintenance_rate=maintenance_rate,
            plusvalia_annual=plusvalia_rate,
        ),
        "display_currency": display_currency,
        "projection_years": projection_years,
        "scraped_data": scraped_data,
    }


# =============================================================================
# MAIN AREA - RESULTADOS
# =============================================================================

def render_kpi_cards(metrics: InvestmentMetrics, calc: RealEstateCalculator, currency: str):
    """Renderizar tarjetas de KPIs principales"""

    st.header("📊 Métricas Clave de Inversión")

    # Fila 1: Valores principales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if currency == "EUR":
            st.metric("💵 Precio Total", f"€{metrics.precio_total_eur:,.0f}")
        elif currency == "UF":
            st.metric("💵 Precio Total", f"UF {metrics.precio_total_uf:,.0f}")
        else:
            clp = calc.uf_to_clp(metrics.precio_total_uf)
            st.metric("💵 Precio Total", f"${clp:,.0f}")

    with col2:
        if currency == "EUR":
            st.metric("🏦 Inversión Inicial (CAPEX)", f"€{metrics.inversion_inicial_eur:,.0f}")
        elif currency == "UF":
            st.metric("🏦 Inversión Inicial (CAPEX)", f"UF {metrics.inversion_inicial_uf:,.0f}")
        else:
            clp = calc.uf_to_clp(metrics.inversion_inicial_uf)
            st.metric("🏦 Inversión Inicial (CAPEX)", f"${clp:,.0f}")

    with col3:
        if currency == "EUR":
            st.metric("📅 Dividendo Mensual", f"€{metrics.dividendo_mensual_eur:,.0f}")
        elif currency == "UF":
            st.metric("📅 Dividendo Mensual", f"UF {metrics.dividendo_mensual_uf:,.2f}")
        else:
            clp = calc.uf_to_clp(metrics.dividendo_mensual_uf)
            st.metric("📅 Dividendo Mensual", f"${clp:,.0f}")

    with col4:
        # Cash Flow con color
        cf = metrics.cashflow_mensual_eur if currency == "EUR" else metrics.cashflow_mensual_clp
        cf_formatted = f"€{cf:,.0f}" if currency == "EUR" else f"${cf:,.0f}"

        delta_color = "normal" if cf >= 0 else "inverse"
        st.metric(
            "💸 Cash Flow Mensual",
            cf_formatted,
            delta="Positivo" if cf >= 0 else "Negativo",
            delta_color=delta_color
        )

    # Fila 2: Métricas de retorno
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        cap_rate_pct = metrics.cap_rate * 100
        cap_rate_color = "🟢" if cap_rate_pct >= 5 else "🟡" if cap_rate_pct >= 3 else "🔴"
        st.metric(
            f"{cap_rate_color} Cap Rate",
            f"{cap_rate_pct:.2f}%",
            help="NOI Anual / Precio. >5% es bueno, <3% es bajo."
        )

    with col2:
        coc_pct = metrics.cash_on_cash * 100
        coc_color = "🟢" if coc_pct >= 5 else "🟡" if coc_pct >= 0 else "🔴"
        st.metric(
            f"{coc_color} Cash-on-Cash",
            f"{coc_pct:.2f}%",
            help="Cash Flow Anual / CAPEX. >5% es bueno."
        )

    with col3:
        if metrics.irr_5_years:
            irr_pct = metrics.irr_5_years * 100
            irr_color = "🟢" if irr_pct >= 8 else "🟡" if irr_pct >= 4 else "🔴"
            st.metric(
                f"{irr_color} TIR 5 Años",
                f"{irr_pct:.2f}%",
                help="Tasa Interna de Retorno a 5 años (incluye plusvalía)"
            )
        else:
            st.metric("TIR 5 Años", "N/A")

    with col4:
        if metrics.irr_10_years:
            irr_pct = metrics.irr_10_years * 100
            irr_color = "🟢" if irr_pct >= 8 else "🟡" if irr_pct >= 4 else "🔴"
            st.metric(
                f"{irr_color} TIR 10 Años",
                f"{irr_pct:.2f}%",
                help="Tasa Interna de Retorno a 10 años"
            )
        else:
            st.metric("TIR 10 Años", "N/A")


def render_cashflow_warning(metrics: InvestmentMetrics, currency: str):
    """Mostrar advertencia si el cash flow es negativo"""

    if not metrics.is_cashflow_positive:
        cf = abs(metrics.cashflow_mensual_eur) if currency == "EUR" else abs(metrics.cashflow_mensual_clp)
        symbol = "€" if currency == "EUR" else "$"

        st.error(f"""
        ⚠️ **ADVERTENCIA: Cash Flow Negativo**

        Esta propiedad requiere una **inyección de capital mensual** de aproximadamente **{symbol}{cf:,.0f}**.

        Esto significa que después de pagar el dividendo, gastos operativos y provisiones,
        necesitarás aportar dinero adicional cada mes para cubrir la diferencia.

        **Consideraciones:**
        - El retorno viene principalmente de la **plusvalía** (apreciación del inmueble)
        - Es común en mercados como Santiago donde los precios son altos respecto a los arriendos
        - Evalúa si tienes la capacidad financiera para sostener este gasto mensual
        """)
    else:
        st.success(f"""
        ✅ **Cash Flow Positivo**

        Esta propiedad genera un flujo de caja positivo después de todos los gastos.
        """)


def render_breakdown_tables(metrics: InvestmentMetrics, calc: RealEstateCalculator, currency: str):
    """Renderizar tablas de desglose"""

    st.header("📋 Desglose Detallado")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Inversión Inicial (CAPEX)")

        capex_data = []
        for key, value_uf in metrics.capex_breakdown.to_dict().items():
            if currency == "EUR":
                value_display = f"€{calc.uf_to_eur(value_uf):,.2f}"
            elif currency == "UF":
                value_display = f"UF {value_uf:,.2f}"
            else:
                value_display = f"${calc.uf_to_clp(value_uf):,.0f}"

            capex_data.append({"Concepto": key, "Monto": value_display})

        st.table(pd.DataFrame(capex_data))

    with col2:
        st.subheader("Gastos Mensuales (OPEX)")

        opex_data = []
        for key, value_clp in metrics.opex_breakdown.to_dict().items():
            if currency == "EUR":
                value_display = f"€{calc.clp_to_eur(value_clp):,.2f}"
            elif currency == "UF":
                value_display = f"UF {calc.clp_to_uf(value_clp):,.4f}"
            else:
                value_display = f"${value_clp:,.0f}"

            opex_data.append({"Concepto": key, "Monto/mes": value_display})

        st.table(pd.DataFrame(opex_data))

    # Desglose del dividendo
    st.subheader("Desglose del Dividendo Hipotecario")

    dividendo_data = [
        {
            "Componente": "Cuota Base (Capital + Interés)",
            "UF/mes": f"UF {metrics.mortgage_payment.cuota_base_uf:.4f}",
            "EUR/mes": f"€{calc.uf_to_eur(metrics.mortgage_payment.cuota_base_uf):,.2f}"
        },
        {
            "Componente": "Seguro Desgravamen",
            "UF/mes": f"UF {metrics.mortgage_payment.seguro_desgravamen_uf:.4f}",
            "EUR/mes": f"€{calc.uf_to_eur(metrics.mortgage_payment.seguro_desgravamen_uf):,.2f}"
        },
        {
            "Componente": "Seguro Incendio/Sismo",
            "UF/mes": f"UF {metrics.mortgage_payment.seguro_incendio_uf:.4f}",
            "EUR/mes": f"€{calc.uf_to_eur(metrics.mortgage_payment.seguro_incendio_uf):,.2f}"
        },
        {
            "Componente": "TOTAL DIVIDENDO",
            "UF/mes": f"UF {metrics.mortgage_payment.dividendo_total_uf:.4f}",
            "EUR/mes": f"€{calc.uf_to_eur(metrics.mortgage_payment.dividendo_total_uf):,.2f}"
        },
    ]

    st.table(pd.DataFrame(dividendo_data))


def render_projection_charts(
    calc: RealEstateCalculator,
    property_input: PropertyInput,
    mortgage_input: MortgageInput,
    operating_input: OperatingInput,
    years: int,
    currency: str
):
    """Renderizar gráficos de proyección"""

    st.header("📈 Proyecciones a Largo Plazo")

    # Generar datos de proyección
    credito_uf = property_input.precio_uf * (1 - mortgage_input.pie_percent)

    # Tabla de amortización
    amortization = calc.generate_amortization_schedule(
        principal_uf=credito_uf,
        rate_annual=mortgage_input.tasa_anual,
        years=mortgage_input.plazo_anos
    )

    # Proyección de valor
    property_values = calc.project_property_value(
        initial_value_uf=property_input.precio_uf,
        years=years,
        plusvalia_rate=operating_input.plusvalia_annual
    )

    # Proyección de equity
    equity_projection = calc.project_equity(property_values, amortization)

    # Preparar datos para gráfico
    chart_data = []
    for proj in equity_projection[:years + 1]:
        year = proj["year"]

        if currency == "EUR":
            prop_value = calc.uf_to_eur(proj["property_value_uf"])
            debt = calc.uf_to_eur(proj["debt_uf"])
            equity = calc.uf_to_eur(proj["equity_uf"])
        elif currency == "UF":
            prop_value = proj["property_value_uf"]
            debt = proj["debt_uf"]
            equity = proj["equity_uf"]
        else:
            prop_value = calc.uf_to_clp(proj["property_value_uf"])
            debt = calc.uf_to_clp(proj["debt_uf"])
            equity = calc.uf_to_clp(proj["equity_uf"])

        chart_data.append({
            "Año": year,
            "Valor Propiedad": prop_value,
            "Deuda Hipotecaria": debt,
            "Equity (Patrimonio)": equity,
        })

    df = pd.DataFrame(chart_data)

    # Gráfico principal
    fig = go.Figure()

    # Valor de la propiedad
    fig.add_trace(go.Scatter(
        x=df["Año"],
        y=df["Valor Propiedad"],
        name="Valor Propiedad",
        mode="lines+markers",
        line=dict(color="#2E86AB", width=3),
        fill="tozeroy",
        fillcolor="rgba(46, 134, 171, 0.1)"
    ))

    # Deuda hipotecaria
    fig.add_trace(go.Scatter(
        x=df["Año"],
        y=df["Deuda Hipotecaria"],
        name="Deuda Hipotecaria",
        mode="lines+markers",
        line=dict(color="#E94F37", width=3),
    ))

    # Equity
    fig.add_trace(go.Scatter(
        x=df["Año"],
        y=df["Equity (Patrimonio)"],
        name="Equity (Patrimonio)",
        mode="lines+markers",
        line=dict(color="#28A745", width=3),
        fill="tozeroy",
        fillcolor="rgba(40, 167, 69, 0.2)"
    ))

    currency_symbol = {"EUR": "€", "UF": "UF ", "CLP": "$"}[currency]

    fig.update_layout(
        title=f"Proyección de Patrimonio a {years} Años",
        xaxis_title="Año",
        yaxis_title=f"Valor ({currency})",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        yaxis=dict(tickformat=","),
        height=500,
    )

    st.plotly_chart(fig, use_container_width=True)

    # Tabla resumen
    st.subheader("Resumen por Año")

    display_df = df.copy()
    if currency == "EUR":
        for col in ["Valor Propiedad", "Deuda Hipotecaria", "Equity (Patrimonio)"]:
            display_df[col] = display_df[col].apply(lambda x: f"€{x:,.0f}")
    elif currency == "UF":
        for col in ["Valor Propiedad", "Deuda Hipotecaria", "Equity (Patrimonio)"]:
            display_df[col] = display_df[col].apply(lambda x: f"UF {x:,.0f}")
    else:
        for col in ["Valor Propiedad", "Deuda Hipotecaria", "Equity (Patrimonio)"]:
            display_df[col] = display_df[col].apply(lambda x: f"${x:,.0f}")

    st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_cashflow_chart(
    metrics: InvestmentMetrics,
    calc: RealEstateCalculator,
    property_input: PropertyInput,
    currency: str
):
    """Renderizar gráfico de flujo de caja mensual"""

    st.subheader("Flujo de Caja Mensual")

    # Datos del flujo
    arriendo = property_input.arriendo_clp
    opex = metrics.opex_breakdown.total_clp
    dividendo = calc.uf_to_clp(metrics.dividendo_mensual_uf)
    noi = metrics.noi_mensual_clp
    cashflow = metrics.cashflow_mensual_clp

    if currency == "EUR":
        arriendo = calc.clp_to_eur(arriendo)
        opex = calc.clp_to_eur(opex)
        dividendo = calc.clp_to_eur(dividendo)
        noi = calc.clp_to_eur(noi)
        cashflow = calc.clp_to_eur(cashflow)
        symbol = "€"
    elif currency == "UF":
        arriendo = calc.clp_to_uf(arriendo)
        opex = calc.clp_to_uf(opex)
        dividendo = calc.clp_to_uf(dividendo)
        noi = calc.clp_to_uf(noi)
        cashflow = calc.clp_to_uf(cashflow)
        symbol = "UF "
    else:
        symbol = "$"

    # Gráfico de cascada
    fig = go.Figure(go.Waterfall(
        name="Flujo de Caja",
        orientation="v",
        measure=["absolute", "relative", "relative", "total", "relative", "total"],
        x=["Arriendo", "Gastos Operativos", "NOI", "NOI Total", "Dividendo", "Cash Flow"],
        y=[arriendo, -opex, 0, noi, -dividendo, 0],
        textposition="outside",
        text=[
            f"{symbol}{arriendo:,.0f}",
            f"-{symbol}{opex:,.0f}",
            "",
            f"{symbol}{noi:,.0f}",
            f"-{symbol}{dividendo:,.0f}",
            f"{symbol}{cashflow:,.0f}"
        ],
        connector={"line": {"color": "rgb(63, 63, 63)"}},
        increasing={"marker": {"color": "#28A745"}},
        decreasing={"marker": {"color": "#DC3545"}},
        totals={"marker": {"color": "#2E86AB"}},
    ))

    fig.update_layout(
        title="Cascada de Flujo de Caja Mensual",
        showlegend=False,
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# MARKET INTELLIGENCE SECTION
# =============================================================================

def render_market_intelligence(
    property_input: PropertyInput,
    scraped_data: Optional[ScrapedProperty],
    currency: str,
    calc: RealEstateCalculator
):
    """Renderizar sección de inteligencia de mercado"""

    st.header("🧠 Inteligencia de Mercado")

    # Obtener datos
    mi = MarketIntelligence()

    # Determinar dormitorios y baños
    dormitorios = 2
    banos = 1
    if scraped_data:
        dormitorios = scraped_data.habitaciones or 2
        banos = scraped_data.banos or 1

    # Generar reporte
    report = mi.generate_report(
        precio_uf=property_input.precio_uf,
        superficie_m2=property_input.superficie_m2,
        comuna=property_input.comuna,
        dormitorios=dormitorios,
        banos=banos,
    )

    # Layout en 3 columnas
    col1, col2, col3 = st.columns(3)

    # --- Análisis de Arriendo ---
    with col1:
        st.subheader("🏷️ Arriendo Sugerido")

        rent = report.rent_analysis
        if rent:
            # Tarjeta con el arriendo sugerido
            st.metric(
                "Arriendo Recomendado",
                f"${rent.suggested_rent_clp:,.0f} CLP",
                delta=f"€{calc.clp_to_eur(rent.suggested_rent_clp):,.0f}/mes",
                delta_color="off"
            )

            # Detalles
            st.markdown(f"""
            **Análisis de {rent.comparables_count} comparables:**
            - Promedio: ${rent.average_rent_clp:,.0f} CLP
            - Mediana: ${rent.median_rent_clp:,.0f} CLP
            - Rango: ${rent.min_rent_clp:,.0f} - ${rent.max_rent_clp:,.0f}
            - Precio/m²: ${rent.average_price_m2:,.0f} CLP/m²

            *{rent.methodology}*
            """)

            # Comparación con input actual
            diff = property_input.arriendo_clp - rent.suggested_rent_clp
            if abs(diff) > 50000:
                if diff > 0:
                    st.warning(f"⚠️ Tu estimación (${property_input.arriendo_clp:,.0f}) está ${diff:,.0f} sobre el mercado")
                else:
                    st.info(f"ℹ️ Tu estimación (${property_input.arriendo_clp:,.0f}) está ${abs(diff):,.0f} bajo el mercado")

    # --- Análisis de Conectividad ---
    with col2:
        st.subheader("🚇 Conectividad Metro")

        loc = report.location_analysis
        if loc and loc.nearest_station:
            # Badge de conectividad
            if loc.connectivity_level == ConnectivityLevel.HIGH:
                st.success("🟢 ALTA CONECTIVIDAD")
            elif loc.connectivity_level == ConnectivityLevel.MEDIUM:
                st.warning("🟡 MEDIA CONECTIVIDAD")
            elif loc.connectivity_level == ConnectivityLevel.LOW:
                st.info("🔵 BAJA CONECTIVIDAD")
            else:
                st.error("🔴 SIN METRO CERCANO")

            st.metric(
                f"Metro {loc.nearest_station.name}",
                f"{loc.distance_meters:.0f} m",
                delta=f"~{loc.walking_time_minutes} min a pie",
                delta_color="off"
            )

            st.markdown(f"""
            **Línea:** {loc.nearest_station.line}

            **Líneas accesibles:** {', '.join(loc.metro_lines_nearby) if loc.metro_lines_nearby else 'N/A'}

            **Estaciones cercanas:** {len(loc.nearby_stations)}
            """)
        else:
            st.warning("No se encontró información de Metro para esta ubicación")

    # --- Análisis de Precio ---
    with col3:
        st.subheader("💰 Precio vs Mercado")

        price = report.price_analysis
        if price:
            # Badge de posición de precio
            if price.price_position == PricePosition.BELOW_MARKET:
                st.success("🟢 OPORTUNIDAD")
            elif price.price_position == PricePosition.AT_MARKET:
                st.info("🔵 PRECIO JUSTO")
            elif price.price_position == PricePosition.ABOVE_MARKET:
                st.warning("🟡 SOBRE MERCADO")
            else:
                st.error("🔴 PRECIO PREMIUM")

            st.metric(
                "UF/m² Propiedad",
                f"{price.uf_per_m2:.1f} UF/m²",
                delta=f"{price.price_diff_percent:+.1f}% vs mercado",
                delta_color="inverse" if price.price_diff_percent > 0 else "normal"
            )

            st.markdown(f"""
            **Promedio {property_input.comuna}:** {price.commune_average_uf_m2:.0f} UF/m²

            **Diferencia:** {price.price_diff_uf_m2:+.1f} UF/m²

            ---
            *{price.analysis_text}*
            """)

    # Separador
    st.markdown("---")


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    """Función principal de la aplicación"""

    # Título principal
    st.title("🏠 Chile Real Estate Investment Calculator")
    st.markdown("**Dashboard para evaluar inversiones inmobiliarias en Chile**")
    st.markdown("---")

    # Obtener tasas de cambio
    rates = get_currency_rates()

    # Crear calculadora
    calc = RealEstateCalculator(rates)

    # Renderizar sidebar y obtener inputs
    inputs = render_sidebar(rates)

    # Ejecutar análisis
    try:
        metrics = calc.analyze_investment(
            property_input=inputs["property_input"],
            mortgage_input=inputs["mortgage_input"],
            operating_input=inputs["operating_input"]
        )

        # Renderizar resultados
        render_kpi_cards(metrics, calc, inputs["display_currency"])

        render_cashflow_warning(metrics, inputs["display_currency"])

        # Sección de Inteligencia de Mercado
        render_market_intelligence(
            property_input=inputs["property_input"],
            scraped_data=inputs.get("scraped_data"),
            currency=inputs["display_currency"],
            calc=calc
        )

        # Gráficos
        col1, col2 = st.columns([2, 1])

        with col1:
            render_projection_charts(
                calc=calc,
                property_input=inputs["property_input"],
                mortgage_input=inputs["mortgage_input"],
                operating_input=inputs["operating_input"],
                years=inputs["projection_years"],
                currency=inputs["display_currency"]
            )

        with col2:
            render_cashflow_chart(
                metrics=metrics,
                calc=calc,
                property_input=inputs["property_input"],
                currency=inputs["display_currency"]
            )

        # Tablas de desglose
        render_breakdown_tables(metrics, calc, inputs["display_currency"])

        # Footer con información
        st.markdown("---")
        st.markdown("""
        **Notas importantes:**
        - Los cálculos son estimaciones basadas en los parámetros ingresados
        - Consulte con un asesor financiero antes de tomar decisiones de inversión
        - Las tasas de cambio se actualizan cada hora desde mindicador.cl
        - El scraping de MercadoLibre puede no funcionar en todos los entornos
        """)

    except Exception as e:
        st.error(f"Error en el análisis: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
