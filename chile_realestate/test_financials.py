"""
Tests Unitarios para el Motor Financiero
=========================================

Valida todos los cálculos financieros del módulo financials.py
"""

import pytest
from datetime import datetime
from financials import (
    CurrencyRates,
    PropertyInput,
    MortgageInput,
    OperatingInput,
    RealEstateCalculator,
    FIXED_COSTS_UF,
    MARKET_RATES,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_rates():
    """Tasas de cambio de prueba (valores fijos para tests determinísticos)"""
    return CurrencyRates(
        uf_clp=38000.0,      # 1 UF = 38,000 CLP
        eur_clp=1000.0,      # 1 EUR = 1,000 CLP
        usd_clp=950.0,       # 1 USD = 950 CLP
        fecha=datetime(2024, 1, 15)
    )


@pytest.fixture
def calculator(mock_rates):
    """Calculadora con tasas fijas"""
    return RealEstateCalculator(mock_rates)


@pytest.fixture
def sample_property():
    """Propiedad de ejemplo para tests"""
    return PropertyInput(
        precio_uf=5000.0,
        arriendo_clp=800000.0,
        gastos_comunes_clp=80000.0,
        superficie_m2=65.0,
        comuna="Las Condes"
    )


@pytest.fixture
def sample_mortgage():
    """Configuración de crédito estándar"""
    return MortgageInput(
        pie_percent=0.30,
        tasa_anual=4.5,
        plazo_anos=20
    )


@pytest.fixture
def sample_operating():
    """Configuración operativa estándar"""
    return OperatingInput(
        vacancy_rate=0.05,
        property_mgmt_rate=0.10,
        maintenance_rate=0.05,
        plusvalia_annual=0.02
    )


# =============================================================================
# TESTS DE CONVERSIÓN DE MONEDAS
# =============================================================================

class TestCurrencyConversions:
    """Tests para conversiones de moneda"""

    def test_uf_to_clp(self, calculator):
        """1 UF = 38,000 CLP"""
        assert calculator.uf_to_clp(1.0) == 38000.0
        assert calculator.uf_to_clp(5000.0) == 190_000_000.0

    def test_clp_to_uf(self, calculator):
        """38,000 CLP = 1 UF"""
        assert calculator.clp_to_uf(38000.0) == 1.0
        assert calculator.clp_to_uf(190_000_000.0) == 5000.0

    def test_uf_to_eur(self, calculator):
        """1 UF = 38 EUR (38000/1000)"""
        assert calculator.uf_to_eur(1.0) == 38.0
        assert calculator.uf_to_eur(5000.0) == 190_000.0

    def test_clp_to_eur(self, calculator):
        """1000 CLP = 1 EUR"""
        assert calculator.clp_to_eur(1000.0) == 1.0
        assert calculator.clp_to_eur(800000.0) == 800.0

    def test_eur_to_clp(self, calculator):
        """1 EUR = 1000 CLP"""
        assert calculator.eur_to_clp(1.0) == 1000.0

    def test_eur_to_uf(self, calculator):
        """38 EUR = 1 UF"""
        assert abs(calculator.eur_to_uf(38.0) - 1.0) < 0.001

    def test_currency_rates_derived_properties(self, mock_rates):
        """Verificar propiedades derivadas de CurrencyRates"""
        # UF en EUR
        assert mock_rates.uf_eur == 38.0  # 38000/1000
        # CLP en EUR
        assert mock_rates.clp_eur == 0.001  # 1/1000


# =============================================================================
# TESTS DE CÁLCULO DE HIPOTECA
# =============================================================================

class TestMortgageCalculation:
    """Tests para cálculo de crédito hipotecario"""

    def test_mortgage_payment_structure(self, calculator):
        """Verificar estructura del dividendo"""
        payment = calculator.calculate_mortgage_payment(
            principal_uf=3500.0,  # 70% de 5000 UF
            rate_annual=4.5,
            years=20,
            property_value_uf=5000.0
        )

        # Verificar que todos los componentes están presentes
        assert payment.cuota_base_uf > 0
        assert payment.seguro_desgravamen_uf > 0
        assert payment.seguro_incendio_uf > 0
        assert payment.dividendo_total_uf > payment.cuota_base_uf

    def test_mortgage_payment_formula(self, calculator):
        """Verificar fórmula de amortización francesa"""
        # Caso conocido: 3500 UF, 4.5% anual, 20 años
        payment = calculator.calculate_mortgage_payment(
            principal_uf=3500.0,
            rate_annual=4.5,
            years=20,
            property_value_uf=5000.0
        )

        # La cuota base debería estar alrededor de 22.14 UF
        # (calculado manualmente con fórmula PMT)
        assert 21.5 < payment.cuota_base_uf < 22.5

    def test_mortgage_insurance_desgravamen(self, calculator):
        """Verificar cálculo de seguro de desgravamen"""
        payment = calculator.calculate_mortgage_payment(
            principal_uf=3500.0,
            rate_annual=4.5,
            years=20,
            property_value_uf=5000.0
        )

        # Desgravamen = 0.025% del saldo = 3500 * 0.00025 = 0.875 UF
        expected = 3500.0 * MARKET_RATES["desgravamen_monthly"]
        assert abs(payment.seguro_desgravamen_uf - expected) < 0.01

    def test_mortgage_insurance_fire(self, calculator):
        """Verificar cálculo de seguro incendio/sismo"""
        payment = calculator.calculate_mortgage_payment(
            principal_uf=3500.0,
            rate_annual=4.5,
            years=20,
            property_value_uf=5000.0
        )

        # Incendio = 0.02% del valor = 5000 * 0.0002 = 1.0 UF
        expected = 5000.0 * MARKET_RATES["incendio_sismo_monthly"]
        assert abs(payment.seguro_incendio_uf - expected) < 0.01

    def test_higher_rate_higher_payment(self, calculator):
        """Mayor tasa = mayor dividendo"""
        payment_low = calculator.calculate_mortgage_payment(
            principal_uf=3500.0, rate_annual=3.5, years=20, property_value_uf=5000.0
        )
        payment_high = calculator.calculate_mortgage_payment(
            principal_uf=3500.0, rate_annual=5.5, years=20, property_value_uf=5000.0
        )

        assert payment_high.cuota_base_uf > payment_low.cuota_base_uf

    def test_longer_term_lower_payment(self, calculator):
        """Mayor plazo = menor cuota mensual"""
        payment_short = calculator.calculate_mortgage_payment(
            principal_uf=3500.0, rate_annual=4.5, years=15, property_value_uf=5000.0
        )
        payment_long = calculator.calculate_mortgage_payment(
            principal_uf=3500.0, rate_annual=4.5, years=25, property_value_uf=5000.0
        )

        assert payment_long.cuota_base_uf < payment_short.cuota_base_uf

    def test_amortization_schedule_length(self, calculator):
        """Verificar longitud de tabla de amortización"""
        schedule = calculator.generate_amortization_schedule(
            principal_uf=3500.0,
            rate_annual=4.5,
            years=20
        )

        # 20 años * 12 meses = 240 cuotas
        assert len(schedule) == 240

    def test_amortization_schedule_final_balance(self, calculator):
        """El saldo final debe ser cercano a cero"""
        schedule = calculator.generate_amortization_schedule(
            principal_uf=3500.0,
            rate_annual=4.5,
            years=20
        )

        # Último saldo debe ser ~0
        assert schedule[-1]["saldo_uf"] < 0.1


# =============================================================================
# TESTS DE CAPEX (INVERSIÓN INICIAL)
# =============================================================================

class TestCapexCalculation:
    """Tests para cálculo de inversión inicial"""

    def test_capex_pie_calculation(self, calculator):
        """Verificar cálculo del pie"""
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.30
        )

        # Pie = 5000 * 0.30 = 1500 UF
        assert capex.pie_uf == 1500.0

    def test_capex_impuesto_mutuo(self, calculator):
        """Verificar impuesto al mutuo (0.8% del crédito)"""
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.30
        )

        # Crédito = 5000 - 1500 = 3500 UF
        # Impuesto = 3500 * 0.008 = 28 UF
        expected = 3500.0 * MARKET_RATES["impuesto_mutuo"]
        assert capex.impuesto_mutuo_uf == expected

    def test_capex_fixed_costs(self, calculator):
        """Verificar gastos fijos"""
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.30
        )

        assert capex.tasacion_uf == FIXED_COSTS_UF["tasacion"]
        assert capex.estudio_titulos_uf == FIXED_COSTS_UF["estudio_titulos"]
        assert capex.borrador_escritura_uf == FIXED_COSTS_UF["borrador_escritura"]
        assert capex.notaria_uf == FIXED_COSTS_UF["notaria"]

    def test_capex_cbrs_calculation(self, calculator):
        """Verificar CBRS (0.5% con tope)"""
        # Propiedad de 5000 UF
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.30
        )

        # CBRS = min(5000 * 0.005, 50) = min(25, 50) = 25 UF
        expected = min(5000.0 * MARKET_RATES["cbrs_rate"], MARKET_RATES["cbrs_tope_uf"])
        assert capex.cbrs_uf == expected

    def test_capex_cbrs_tope(self, calculator):
        """Verificar tope de CBRS en propiedades caras"""
        # Propiedad de 20000 UF (debería topar)
        capex = calculator.calculate_initial_investment(
            property_value_uf=20000.0,
            pie_percent=0.30
        )

        # CBRS = min(20000 * 0.005, 50) = min(100, 50) = 50 UF
        assert capex.cbrs_uf == MARKET_RATES["cbrs_tope_uf"]

    def test_capex_corretaje_with_iva(self, calculator):
        """Verificar corretaje (2% + IVA 19%)"""
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.30
        )

        # Corretaje = 5000 * 0.02 * 1.19 = 119 UF
        expected = 5000.0 * MARKET_RATES["corretaje_rate"] * (1 + MARKET_RATES["iva"])
        assert capex.corretaje_uf == expected

    def test_capex_total_calculation(self, calculator):
        """Verificar suma total de CAPEX"""
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.30
        )

        # Verificar que total = suma de componentes
        expected_total = (
            capex.pie_uf +
            capex.impuesto_mutuo_uf +
            capex.tasacion_uf +
            capex.estudio_titulos_uf +
            capex.borrador_escritura_uf +
            capex.notaria_uf +
            capex.cbrs_uf +
            capex.corretaje_uf
        )

        assert capex.total_uf == expected_total

    def test_capex_gastos_cierre(self, calculator):
        """Verificar gastos de cierre (sin pie)"""
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.30
        )

        assert capex.gastos_cierre_uf == capex.total_uf - capex.pie_uf


# =============================================================================
# TESTS DE OPEX (GASTOS OPERATIVOS)
# =============================================================================

class TestOpexCalculation:
    """Tests para cálculo de gastos operativos"""

    def test_opex_contribuciones(self, calculator, sample_operating):
        """Verificar contribuciones (0.75% anual mensualizado)"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        # Valor propiedad en CLP = 5000 * 38000 = 190,000,000
        # Contribuciones anuales = 190,000,000 * 0.0075 = 1,425,000
        # Mensuales = 1,425,000 / 12 = 118,750 CLP
        valor_clp = 5000.0 * 38000.0
        expected = (valor_clp * MARKET_RATES["contribuciones_annual"]) / 12
        assert abs(opex.contribuciones_clp - expected) < 1

    def test_opex_administracion(self, calculator, sample_operating):
        """Verificar administración (10% + IVA)"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        # Admin = 800000 * 0.10 * 1.19 = 95,200 CLP
        expected = 800000.0 * sample_operating.property_mgmt_rate * (1 + MARKET_RATES["iva"])
        assert abs(opex.administracion_clp - expected) < 1

    def test_opex_mantencion(self, calculator, sample_operating):
        """Verificar mantención (5% del arriendo)"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        # Mantención = 800000 * 0.05 = 40,000 CLP
        expected = 800000.0 * sample_operating.maintenance_rate
        assert abs(opex.mantencion_clp - expected) < 1

    def test_opex_vacancia(self, calculator, sample_operating):
        """Verificar vacancia (5% del arriendo)"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        # Vacancia = 800000 * 0.05 = 40,000 CLP
        expected = 800000.0 * sample_operating.vacancy_rate
        assert abs(opex.vacancia_clp - expected) < 1

    def test_opex_gastos_comunes(self, calculator, sample_operating):
        """Verificar gastos comunes"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        assert opex.gastos_comunes_clp == 80000.0

    def test_opex_total(self, calculator, sample_operating):
        """Verificar suma total de OPEX"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        expected_total = (
            opex.contribuciones_clp +
            opex.administracion_clp +
            opex.mantencion_clp +
            opex.vacancia_clp +
            opex.gastos_comunes_clp
        )

        assert opex.total_clp == expected_total


# =============================================================================
# TESTS DE FLUJO DE CAJA
# =============================================================================

class TestCashflowCalculation:
    """Tests para cálculo de flujo de caja"""

    def test_noi_calculation(self, calculator, sample_operating):
        """Verificar NOI = Arriendo - OPEX"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        mortgage = calculator.calculate_mortgage_payment(
            principal_uf=3500.0,
            rate_annual=4.5,
            years=20,
            property_value_uf=5000.0
        )

        noi, cashflow = calculator.calculate_monthly_cashflow(
            arriendo_clp=800000.0,
            opex=opex,
            mortgage=mortgage
        )

        expected_noi = 800000.0 - opex.total_clp
        assert noi == expected_noi

    def test_cashflow_calculation(self, calculator, sample_operating):
        """Verificar Cashflow = NOI - Dividendo"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=80000.0,
            operating=sample_operating
        )

        mortgage = calculator.calculate_mortgage_payment(
            principal_uf=3500.0,
            rate_annual=4.5,
            years=20,
            property_value_uf=5000.0
        )

        noi, cashflow = calculator.calculate_monthly_cashflow(
            arriendo_clp=800000.0,
            opex=opex,
            mortgage=mortgage
        )

        dividendo_clp = calculator.uf_to_clp(mortgage.dividendo_total_uf)
        expected_cashflow = noi - dividendo_clp

        assert abs(cashflow - expected_cashflow) < 1


# =============================================================================
# TESTS DE MÉTRICAS DE RETORNO
# =============================================================================

class TestReturnMetrics:
    """Tests para métricas de retorno"""

    def test_cap_rate_calculation(self, calculator):
        """Verificar Cap Rate = NOI Anual / Valor Propiedad"""
        noi_annual = 5_000_000.0  # 5M CLP
        property_value = 100_000_000.0  # 100M CLP

        cap_rate = calculator.calculate_cap_rate(noi_annual, property_value)

        # Cap Rate = 5M / 100M = 5%
        assert abs(cap_rate - 0.05) < 0.001

    def test_cap_rate_zero_value(self, calculator):
        """Cap Rate debe ser 0 si valor propiedad es 0"""
        cap_rate = calculator.calculate_cap_rate(5_000_000.0, 0)
        assert cap_rate == 0.0

    def test_cash_on_cash_calculation(self, calculator):
        """Verificar Cash-on-Cash = Cashflow Anual / Cash Invertido"""
        cashflow_annual = 2_000_000.0  # 2M CLP
        cash_invested = 50_000_000.0  # 50M CLP

        coc = calculator.calculate_cash_on_cash(cashflow_annual, cash_invested)

        # CoC = 2M / 50M = 4%
        assert abs(coc - 0.04) < 0.001

    def test_cash_on_cash_negative(self, calculator):
        """Cash-on-Cash puede ser negativo"""
        coc = calculator.calculate_cash_on_cash(-1_000_000.0, 50_000_000.0)
        assert coc < 0

    def test_irr_basic_case(self, calculator):
        """Verificar cálculo básico de TIR"""
        # Inversión de 100, flujos de 10 por mes, venta de 120 al final
        cash_invested = 100.0
        monthly_cashflows = [10.0] * 12  # 12 meses de $10
        exit_value = 120.0

        irr = calculator.calculate_irr(cash_invested, monthly_cashflows, exit_value)

        # TIR debe ser positiva y razonable
        assert irr is not None
        assert irr > 0

    def test_irr_negative_case(self, calculator):
        """TIR puede ser negativa con malos flujos"""
        cash_invested = 100.0
        monthly_cashflows = [-5.0] * 12  # Flujos negativos
        exit_value = 80.0  # Pérdida en venta

        irr = calculator.calculate_irr(cash_invested, monthly_cashflows, exit_value)

        if irr is not None:
            assert irr < 0


# =============================================================================
# TESTS DE PROYECCIONES
# =============================================================================

class TestProjections:
    """Tests para proyecciones"""

    def test_property_value_projection(self, calculator):
        """Verificar proyección de valor con plusvalía"""
        values = calculator.project_property_value(
            initial_value_uf=5000.0,
            years=10,
            plusvalia_rate=0.02
        )

        # 11 valores (año 0 al 10)
        assert len(values) == 11

        # Año 0 = valor inicial
        assert values[0] == 5000.0

        # Año 1 = 5000 * 1.02 = 5100
        assert abs(values[1] - 5100.0) < 0.01

        # Año 10 = 5000 * (1.02)^10 ≈ 6094.97
        expected_y10 = 5000.0 * (1.02 ** 10)
        assert abs(values[10] - expected_y10) < 0.01

    def test_equity_projection_structure(self, calculator):
        """Verificar estructura de proyección de equity"""
        # Generar proyección
        values = calculator.project_property_value(5000.0, 10, 0.02)
        schedule = calculator.generate_amortization_schedule(3500.0, 4.5, 20)
        equity = calculator.project_equity(values, schedule)

        # 11 años (0-10)
        assert len(equity) == 11

        # Verificar estructura
        for item in equity:
            assert "year" in item
            assert "property_value_uf" in item
            assert "debt_uf" in item
            assert "equity_uf" in item

    def test_equity_increases_over_time(self, calculator):
        """El equity debe aumentar con el tiempo"""
        values = calculator.project_property_value(5000.0, 10, 0.02)
        schedule = calculator.generate_amortization_schedule(3500.0, 4.5, 20)
        equity = calculator.project_equity(values, schedule)

        # Equity año 10 > Equity año 0
        assert equity[10]["equity_uf"] > equity[0]["equity_uf"]


# =============================================================================
# TESTS DE ANÁLISIS COMPLETO
# =============================================================================

class TestCompleteAnalysis:
    """Tests para análisis de inversión completo"""

    def test_analyze_investment_returns_metrics(
        self, calculator, sample_property, sample_mortgage, sample_operating
    ):
        """Verificar que analyze_investment retorna todas las métricas"""
        metrics = calculator.analyze_investment(
            sample_property,
            sample_mortgage,
            sample_operating
        )

        # Verificar campos principales
        assert metrics.precio_total_uf == sample_property.precio_uf
        assert metrics.precio_total_eur > 0
        assert metrics.inversion_inicial_uf > 0
        assert metrics.dividendo_mensual_uf > 0

        # Verificar métricas de retorno
        assert metrics.cap_rate is not None
        assert metrics.cash_on_cash is not None

        # Verificar desgloses
        assert metrics.capex_breakdown is not None
        assert metrics.opex_breakdown is not None
        assert metrics.mortgage_payment is not None

    def test_analyze_investment_coherence(
        self, calculator, sample_property, sample_mortgage, sample_operating
    ):
        """Verificar coherencia entre métricas"""
        metrics = calculator.analyze_investment(
            sample_property,
            sample_mortgage,
            sample_operating
        )

        # Inversión inicial > Pie
        assert metrics.inversion_inicial_uf > metrics.capex_breakdown.pie_uf

        # NOI > Cashflow (porque dividendo se resta)
        if metrics.dividendo_mensual_uf > 0:
            assert metrics.noi_mensual_clp > metrics.cashflow_mensual_clp

    def test_cashflow_positive_flag(self, calculator, sample_mortgage, sample_operating):
        """Verificar flag de cashflow positivo/negativo"""
        # Caso con arriendo alto (debería ser positivo)
        high_rent = PropertyInput(
            precio_uf=3000.0,
            arriendo_clp=1_500_000.0,  # Arriendo alto
            gastos_comunes_clp=50000.0
        )

        metrics_positive = calculator.analyze_investment(
            high_rent, sample_mortgage, sample_operating
        )

        # Este caso debería tener cashflow positivo
        assert metrics_positive.is_cashflow_positive == (metrics_positive.cashflow_mensual_clp > 0)


# =============================================================================
# TESTS DE EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests para casos límite"""

    def test_zero_gastos_comunes(self, calculator, sample_operating):
        """Propiedad sin gastos comunes"""
        opex = calculator.calculate_monthly_opex(
            property_value_uf=5000.0,
            arriendo_clp=800000.0,
            gastos_comunes_clp=0.0,  # Sin gastos comunes
            operating=sample_operating
        )

        assert opex.gastos_comunes_clp == 0

    def test_high_pie_percentage(self, calculator):
        """Pie del 50%"""
        capex = calculator.calculate_initial_investment(
            property_value_uf=5000.0,
            pie_percent=0.50
        )

        assert capex.pie_uf == 2500.0
        # Impuesto mutuo menor (sobre 2500 UF de crédito)
        assert capex.impuesto_mutuo_uf == 2500.0 * 0.008

    def test_different_vacancy_rates(self, calculator):
        """Diferentes tasas de vacancia"""
        for vacancy in [0.0, 0.05, 0.10, 0.15]:
            operating = OperatingInput(vacancy_rate=vacancy)
            opex = calculator.calculate_monthly_opex(
                property_value_uf=5000.0,
                arriendo_clp=800000.0,
                gastos_comunes_clp=80000.0,
                operating=operating
            )

            expected_vacancia = 800000.0 * vacancy
            assert abs(opex.vacancia_clp - expected_vacancia) < 1


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
