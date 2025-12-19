"""
Market Intelligence Module - Chile Real Estate
==============================================

Este módulo proporciona análisis de mercado para contextualizar
las propiedades inmobiliarias en Chile.

Componentes:
1. MarketCompScraper - Búsqueda de arriendos comparables
2. LocationAnalyzer - Análisis de conectividad (Metro Santiago)
3. PriceAnalyzer - Comparación de precios por comuna

Autor: Dashboard MVP Chile Real Estate
Versión: 1.0.0
"""

import json
import math
import random
import time
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any
from pathlib import Path
from statistics import mean, median, stdev
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES Y DATOS DE REFERENCIA
# =============================================================================

# Precios promedio por comuna en UF/m² (datos de referencia 2024)
# Fuente: Estimaciones basadas en portales inmobiliarios
AVG_PRICE_PER_COMMUNE: Dict[str, float] = {
    # Sector Oriente (más caro)
    "Las Condes": 95.0,
    "Vitacura": 110.0,
    "Lo Barnechea": 85.0,
    "Providencia": 90.0,
    "Ñuñoa": 75.0,
    "La Reina": 70.0,

    # Santiago Centro y alrededores
    "Santiago": 65.0,
    "Independencia": 55.0,
    "Recoleta": 50.0,
    "Quinta Normal": 45.0,
    "Estación Central": 50.0,

    # Sector Sur
    "San Miguel": 55.0,
    "San Joaquín": 45.0,
    "Macul": 55.0,
    "La Florida": 50.0,
    "Puente Alto": 35.0,
    "La Granja": 35.0,
    "La Cisterna": 45.0,
    "San Bernardo": 32.0,

    # Sector Norte
    "Huechuraba": 50.0,
    "Conchalí": 40.0,
    "Renca": 38.0,
    "Quilicura": 40.0,
    "Colina": 45.0,

    # Sector Poniente
    "Maipú": 42.0,
    "Pudahuel": 38.0,
    "Cerrillos": 45.0,
    "Lo Prado": 40.0,
    "Cerro Navia": 35.0,

    # Sector Sur-Oriente
    "Peñalolén": 55.0,
    "La Pintana": 28.0,
    "El Bosque": 35.0,
    "San Ramón": 32.0,

    # Default para comunas no listadas
    "_default": 50.0,
}

# Rangos de arriendo típicos por comuna (CLP/m²/mes)
AVG_RENT_PER_COMMUNE: Dict[str, Tuple[float, float]] = {
    # (min, max) CLP por m² mensual
    "Las Condes": (10000, 15000),
    "Vitacura": (12000, 18000),
    "Lo Barnechea": (9000, 14000),
    "Providencia": (10000, 14000),
    "Ñuñoa": (8000, 12000),
    "La Reina": (8000, 11000),
    "Santiago": (7000, 11000),
    "San Miguel": (7000, 10000),
    "La Florida": (6000, 9000),
    "Maipú": (5500, 8500),
    "Puente Alto": (5000, 7500),
    "_default": (6000, 10000),
}


# =============================================================================
# DATOS DEL METRO DE SANTIAGO
# =============================================================================

# Estaciones del Metro de Santiago con coordenadas (Lat, Lon)
# Líneas 1-6 + estaciones confirmadas de L7
METRO_STATIONS: List[Dict[str, Any]] = [
    # LÍNEA 1 (Roja) - Los Dominicos a San Pablo
    {"name": "Los Dominicos", "line": "L1", "lat": -33.4101, "lon": -70.5241},
    {"name": "Hernando de Magallanes", "line": "L1", "lat": -33.4082, "lon": -70.5359},
    {"name": "Manquehue", "line": "L1", "lat": -33.4028, "lon": -70.5480},
    {"name": "Escuela Militar", "line": "L1", "lat": -33.4025, "lon": -70.5585},
    {"name": "Alcántara", "line": "L1", "lat": -33.4053, "lon": -70.5695},
    {"name": "El Golf", "line": "L1", "lat": -33.4101, "lon": -70.5804},
    {"name": "Tobalaba", "line": "L1", "lat": -33.4187, "lon": -70.5893},
    {"name": "Los Leones", "line": "L1", "lat": -33.4230, "lon": -70.5982},
    {"name": "Pedro de Valdivia", "line": "L1", "lat": -33.4251, "lon": -70.6093},
    {"name": "Manuel Montt", "line": "L1", "lat": -33.4262, "lon": -70.6186},
    {"name": "Salvador", "line": "L1", "lat": -33.4310, "lon": -70.6274},
    {"name": "Baquedano", "line": "L1", "lat": -33.4375, "lon": -70.6350},
    {"name": "Universidad Católica", "line": "L1", "lat": -33.4417, "lon": -70.6421},
    {"name": "Santa Lucía", "line": "L1", "lat": -33.4426, "lon": -70.6478},
    {"name": "Universidad de Chile", "line": "L1", "lat": -33.4432, "lon": -70.6536},
    {"name": "La Moneda", "line": "L1", "lat": -33.4427, "lon": -70.6602},
    {"name": "Los Héroes", "line": "L1", "lat": -33.4467, "lon": -70.6656},
    {"name": "República", "line": "L1", "lat": -33.4503, "lon": -70.6715},
    {"name": "Estación Central", "line": "L1", "lat": -33.4527, "lon": -70.6786},
    {"name": "Unión Latinoamericana", "line": "L1", "lat": -33.4539, "lon": -70.6870},
    {"name": "Alberto Hurtado", "line": "L1", "lat": -33.4556, "lon": -70.6969},
    {"name": "Ecuador", "line": "L1", "lat": -33.4586, "lon": -70.7051},
    {"name": "Las Rejas", "line": "L1", "lat": -33.4631, "lon": -70.7157},
    {"name": "Pajaritos", "line": "L1", "lat": -33.4685, "lon": -70.7289},
    {"name": "Del Sol", "line": "L1", "lat": -33.4688, "lon": -70.7430},
    {"name": "Monte Tabor", "line": "L1", "lat": -33.4687, "lon": -70.7522},
    {"name": "Santiago Bueras", "line": "L1", "lat": -33.4688, "lon": -70.7618},
    {"name": "San Pablo", "line": "L1", "lat": -33.4688, "lon": -70.7730},

    # LÍNEA 2 (Amarilla) - Vespucio Norte a La Cisterna
    {"name": "Vespucio Norte", "line": "L2", "lat": -33.3900, "lon": -70.6200},
    {"name": "Zapadores", "line": "L2", "lat": -33.3960, "lon": -70.6212},
    {"name": "Dorsal", "line": "L2", "lat": -33.4050, "lon": -70.6240},
    {"name": "Einstein", "line": "L2", "lat": -33.4130, "lon": -70.6275},
    {"name": "Cerro Blanco", "line": "L2", "lat": -33.4190, "lon": -70.6345},
    {"name": "Patronato", "line": "L2", "lat": -33.4260, "lon": -70.6392},
    {"name": "Puente Cal y Canto", "line": "L2", "lat": -33.4333, "lon": -70.6440},
    {"name": "Santa Ana", "line": "L2", "lat": -33.4409, "lon": -70.6505},
    {"name": "Parque O'Higgins", "line": "L2", "lat": -33.4630, "lon": -70.6605},
    {"name": "Rondizzoni", "line": "L2", "lat": -33.4710, "lon": -70.6600},
    {"name": "Franklin", "line": "L2", "lat": -33.4790, "lon": -70.6590},
    {"name": "El Llano", "line": "L2", "lat": -33.4890, "lon": -70.6575},
    {"name": "San Miguel", "line": "L2", "lat": -33.4970, "lon": -70.6555},
    {"name": "Departamental", "line": "L2", "lat": -33.5070, "lon": -70.6520},
    {"name": "Ciudad del Niño", "line": "L2", "lat": -33.5150, "lon": -70.6485},
    {"name": "Lo Ovalle", "line": "L2", "lat": -33.5233, "lon": -70.6450},
    {"name": "El Parrón", "line": "L2", "lat": -33.5310, "lon": -70.6435},
    {"name": "La Cisterna", "line": "L2", "lat": -33.5390, "lon": -70.6590},

    # LÍNEA 3 (Café) - Los Libertadores a Fernando Castillo Velasco
    {"name": "Los Libertadores", "line": "L3", "lat": -33.3756, "lon": -70.6585},
    {"name": "Cardenal Caro", "line": "L3", "lat": -33.3830, "lon": -70.6567},
    {"name": "Vivaceta", "line": "L3", "lat": -33.3975, "lon": -70.6545},
    {"name": "Conchalí", "line": "L3", "lat": -33.4030, "lon": -70.6520},
    {"name": "Plaza Chacabuco", "line": "L3", "lat": -33.4195, "lon": -70.6480},
    {"name": "Hospitales", "line": "L3", "lat": -33.4295, "lon": -70.6480},
    {"name": "Cal y Canto", "line": "L3", "lat": -33.4333, "lon": -70.6440},
    {"name": "Plaza de Armas", "line": "L3", "lat": -33.4380, "lon": -70.6505},
    {"name": "Universidad de Chile (L3)", "line": "L3", "lat": -33.4432, "lon": -70.6536},
    {"name": "Parque Almagro", "line": "L3", "lat": -33.4498, "lon": -70.6485},
    {"name": "Matta", "line": "L3", "lat": -33.4595, "lon": -70.6395},
    {"name": "Irarrázaval", "line": "L3", "lat": -33.4535, "lon": -70.6130},
    {"name": "Monseñor Eyzaguirre", "line": "L3", "lat": -33.4545, "lon": -70.5985},
    {"name": "Ñuñoa", "line": "L3", "lat": -33.4555, "lon": -70.5940},
    {"name": "Chile España", "line": "L3", "lat": -33.4555, "lon": -70.5830},
    {"name": "Villa Frei", "line": "L3", "lat": -33.4590, "lon": -70.5725},
    {"name": "Plaza Egaña", "line": "L3", "lat": -33.4545, "lon": -70.5683},
    {"name": "Fernando Castillo Velasco", "line": "L3", "lat": -33.4535, "lon": -70.5540},

    # LÍNEA 4 (Azul) - Tobalaba a Plaza de Puente Alto
    {"name": "Tobalaba (L4)", "line": "L4", "lat": -33.4187, "lon": -70.5893},
    {"name": "Cristóbal Colón", "line": "L4", "lat": -33.4265, "lon": -70.5810},
    {"name": "Francisco Bilbao", "line": "L4", "lat": -33.4380, "lon": -70.5795},
    {"name": "Príncipe de Gales", "line": "L4", "lat": -33.4470, "lon": -70.5780},
    {"name": "Simón Bolívar", "line": "L4", "lat": -33.4515, "lon": -70.5760},
    {"name": "Grecia", "line": "L4", "lat": -33.4590, "lon": -70.5720},
    {"name": "Los Orientales", "line": "L4", "lat": -33.4695, "lon": -70.5665},
    {"name": "Quilín", "line": "L4", "lat": -33.4895, "lon": -70.5605},
    {"name": "Las Torres", "line": "L4", "lat": -33.5010, "lon": -70.5572},
    {"name": "Macul", "line": "L4", "lat": -33.5115, "lon": -70.5545},
    {"name": "Vicuña Mackenna", "line": "L4", "lat": -33.5275, "lon": -70.5905},
    {"name": "Vicente Valdés", "line": "L4", "lat": -33.5380, "lon": -70.5950},
    {"name": "Rojas Magallanes", "line": "L4", "lat": -33.5485, "lon": -70.5995},
    {"name": "Trinidad", "line": "L4", "lat": -33.5590, "lon": -70.6020},
    {"name": "San José de la Estrella", "line": "L4", "lat": -33.5705, "lon": -70.6050},
    {"name": "Los Quillayes", "line": "L4", "lat": -33.5840, "lon": -70.6075},
    {"name": "Elisa Correa", "line": "L4", "lat": -33.5955, "lon": -70.6035},
    {"name": "Hospital Sótero del Río", "line": "L4", "lat": -33.6085, "lon": -70.5975},
    {"name": "Protectora de la Infancia", "line": "L4", "lat": -33.6195, "lon": -70.5920},
    {"name": "Las Mercedes", "line": "L4", "lat": -33.6295, "lon": -70.5865},
    {"name": "Plaza de Puente Alto", "line": "L4", "lat": -33.6100, "lon": -70.5770},

    # LÍNEA 4A (Azul Claro) - Vicuña Mackenna a La Cisterna
    {"name": "Vicuña Mackenna (4A)", "line": "L4A", "lat": -33.5275, "lon": -70.5905},
    {"name": "Los Presidentes", "line": "L4A", "lat": -33.5275, "lon": -70.6100},
    {"name": "Quilín (4A)", "line": "L4A", "lat": -33.5245, "lon": -70.6280},
    {"name": "Santa Julia", "line": "L4A", "lat": -33.5240, "lon": -70.6430},
    {"name": "La Granja", "line": "L4A", "lat": -33.5350, "lon": -70.6505},
    {"name": "Santa Rosa", "line": "L4A", "lat": -33.5390, "lon": -70.6590},
    {"name": "La Cisterna (4A)", "line": "L4A", "lat": -33.5390, "lon": -70.6590},

    # LÍNEA 5 (Verde) - Plaza de Maipú a Vicente Valdés
    {"name": "Plaza de Maipú", "line": "L5", "lat": -33.5098, "lon": -70.7559},
    {"name": "Santiago Bueras (L5)", "line": "L5", "lat": -33.4980, "lon": -70.7445},
    {"name": "Del Sol (L5)", "line": "L5", "lat": -33.4915, "lon": -70.7350},
    {"name": "Monte Tabor (L5)", "line": "L5", "lat": -33.4845, "lon": -70.7248},
    {"name": "Laguna Sur", "line": "L5", "lat": -33.4769, "lon": -70.7152},
    {"name": "Barrancas", "line": "L5", "lat": -33.4720, "lon": -70.7040},
    {"name": "Pudahuel", "line": "L5", "lat": -33.4635, "lon": -70.6880},
    {"name": "San Pablo (L5)", "line": "L5", "lat": -33.4490, "lon": -70.6740},
    {"name": "Lo Prado", "line": "L5", "lat": -33.4440, "lon": -70.6655},
    {"name": "Blanqueado", "line": "L5", "lat": -33.4420, "lon": -70.6560},
    {"name": "Gruta de Lourdes", "line": "L5", "lat": -33.4420, "lon": -70.6475},
    {"name": "Quinta Normal", "line": "L5", "lat": -33.4390, "lon": -70.6585},
    {"name": "Cumming", "line": "L5", "lat": -33.4408, "lon": -70.6525},
    {"name": "Santa Ana (L5)", "line": "L5", "lat": -33.4409, "lon": -70.6505},
    {"name": "Plaza de Armas (L5)", "line": "L5", "lat": -33.4380, "lon": -70.6505},
    {"name": "Bellas Artes", "line": "L5", "lat": -33.4365, "lon": -70.6425},
    {"name": "Baquedano (L5)", "line": "L5", "lat": -33.4375, "lon": -70.6350},
    {"name": "Parque Bustamante", "line": "L5", "lat": -33.4425, "lon": -70.6275},
    {"name": "Santa Isabel", "line": "L5", "lat": -33.4520, "lon": -70.6240},
    {"name": "Ñuble", "line": "L5", "lat": -33.4615, "lon": -70.6195},
    {"name": "Rodrigo de Araya", "line": "L5", "lat": -33.4732, "lon": -70.6115},
    {"name": "Carlos Valdovinos", "line": "L5", "lat": -33.4835, "lon": -70.6050},
    {"name": "Camino Agrícola", "line": "L5", "lat": -33.4930, "lon": -70.5990},
    {"name": "San Joaquín", "line": "L5", "lat": -33.4960, "lon": -70.6213},
    {"name": "Pedrero", "line": "L5", "lat": -33.5010, "lon": -70.6175},
    {"name": "Mirador", "line": "L5", "lat": -33.5085, "lon": -70.6115},
    {"name": "Bellavista de La Florida", "line": "L5", "lat": -33.5180, "lon": -70.6030},
    {"name": "Vicente Valdés (L5)", "line": "L5", "lat": -33.5380, "lon": -70.5950},

    # LÍNEA 6 (Morada) - Cerrillos a Los Leones
    {"name": "Cerrillos", "line": "L6", "lat": -33.4930, "lon": -70.7140},
    {"name": "Lo Valledor", "line": "L6", "lat": -33.4790, "lon": -70.6905},
    {"name": "Pedro Aguirre Cerda", "line": "L6", "lat": -33.4720, "lon": -70.6760},
    {"name": "Franklin (L6)", "line": "L6", "lat": -33.4680, "lon": -70.6635},
    {"name": "Bio Bío", "line": "L6", "lat": -33.4595, "lon": -70.6515},
    {"name": "Ñuñoa (L6)", "line": "L6", "lat": -33.4535, "lon": -70.6125},
    {"name": "Estadio Nacional", "line": "L6", "lat": -33.4620, "lon": -70.6065},
    {"name": "Ñuble (L6)", "line": "L6", "lat": -33.4615, "lon": -70.6195},
    {"name": "Inés de Suárez", "line": "L6", "lat": -33.4350, "lon": -70.6015},
    {"name": "Los Leones (L6)", "line": "L6", "lat": -33.4230, "lon": -70.5982},

    # LÍNEA 7 (Naranja) - Estaciones confirmadas/en construcción
    {"name": "Renca", "line": "L7", "lat": -33.4095, "lon": -70.7245},
    {"name": "Cerro Navia", "line": "L7", "lat": -33.4220, "lon": -70.7200},
    {"name": "Quinta Normal (L7)", "line": "L7", "lat": -33.4345, "lon": -70.6975},
    {"name": "Brasil", "line": "L7", "lat": -33.4420, "lon": -70.6625},
    {"name": "Cumming (L7)", "line": "L7", "lat": -33.4430, "lon": -70.6535},
    {"name": "Irarrázaval (L7)", "line": "L7", "lat": -33.4450, "lon": -70.6245},
    {"name": "Ñuñoa (L7)", "line": "L7", "lat": -33.4535, "lon": -70.5995},
    {"name": "Vitacura", "line": "L7", "lat": -33.3975, "lon": -70.5795},
    {"name": "Estoril", "line": "L7", "lat": -33.3895, "lon": -70.5675},
]


# =============================================================================
# ESTRUCTURAS DE DATOS
# =============================================================================

class ConnectivityLevel(Enum):
    """Nivel de conectividad basado en distancia al Metro"""
    HIGH = "Alta Conectividad"        # < 500m
    MEDIUM = "Media Conectividad"     # 500m - 800m
    LOW = "Baja Conectividad"         # 800m - 1500m
    NONE = "Sin Metro cercano"        # > 1500m


class PricePosition(Enum):
    """Posición del precio respecto al mercado"""
    BELOW_MARKET = "Oportunidad bajo mercado"
    AT_MARKET = "Precio de mercado"
    ABOVE_MARKET = "Sobre precio de mercado"
    PREMIUM = "Precio premium"


@dataclass
class RentComparable:
    """Un arriendo comparable encontrado"""
    precio_clp: float
    superficie_m2: float
    comuna: str
    dormitorios: int
    banos: int
    url: Optional[str] = None
    precio_m2: float = 0.0

    def __post_init__(self):
        if self.superficie_m2 > 0:
            self.precio_m2 = self.precio_clp / self.superficie_m2


@dataclass
class MarketRentAnalysis:
    """Resultado del análisis de arriendos de mercado"""
    comparables_count: int
    average_rent_clp: float
    median_rent_clp: float
    min_rent_clp: float
    max_rent_clp: float
    std_dev_clp: float
    average_price_m2: float
    suggested_rent_clp: float          # Sugerencia conservadora
    suggested_rent_range: Tuple[float, float]
    comparables: List[RentComparable] = field(default_factory=list)
    methodology: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparables_count": self.comparables_count,
            "average_rent_clp": self.average_rent_clp,
            "median_rent_clp": self.median_rent_clp,
            "min_rent_clp": self.min_rent_clp,
            "max_rent_clp": self.max_rent_clp,
            "std_dev_clp": self.std_dev_clp,
            "average_price_m2": self.average_price_m2,
            "suggested_rent_clp": self.suggested_rent_clp,
            "suggested_rent_range": self.suggested_rent_range,
            "methodology": self.methodology,
        }


@dataclass
class MetroStation:
    """Estación de Metro"""
    name: str
    line: str
    lat: float
    lon: float
    distance_m: float = 0.0


@dataclass
class LocationAnalysisResult:
    """Resultado del análisis de ubicación"""
    nearest_station: Optional[MetroStation]
    distance_meters: float
    connectivity_level: ConnectivityLevel
    nearby_stations: List[MetroStation]      # Estaciones en radio de 1.5km
    metro_lines_nearby: List[str]            # Líneas de Metro accesibles
    walking_time_minutes: int                # Estimación a pie
    has_metro_access: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nearest_station": self.nearest_station.name if self.nearest_station else None,
            "nearest_station_line": self.nearest_station.line if self.nearest_station else None,
            "distance_meters": round(self.distance_meters, 0),
            "connectivity_level": self.connectivity_level.value,
            "nearby_stations_count": len(self.nearby_stations),
            "metro_lines_nearby": self.metro_lines_nearby,
            "walking_time_minutes": self.walking_time_minutes,
            "has_metro_access": self.has_metro_access,
        }


@dataclass
class PriceAnalysisResult:
    """Resultado del análisis de precio"""
    uf_per_m2: float
    commune_average_uf_m2: float
    price_position: PricePosition
    price_diff_percent: float              # % diferencia vs mercado
    price_diff_uf_m2: float                # Diferencia en UF/m²
    is_opportunity: bool
    analysis_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uf_per_m2": round(self.uf_per_m2, 2),
            "commune_average_uf_m2": round(self.commune_average_uf_m2, 2),
            "price_position": self.price_position.value,
            "price_diff_percent": round(self.price_diff_percent, 1),
            "price_diff_uf_m2": round(self.price_diff_uf_m2, 2),
            "is_opportunity": self.is_opportunity,
            "analysis_text": self.analysis_text,
        }


@dataclass
class MarketIntelligenceReport:
    """Reporte completo de inteligencia de mercado"""
    rent_analysis: Optional[MarketRentAnalysis]
    location_analysis: Optional[LocationAnalysisResult]
    price_analysis: Optional[PriceAnalysisResult]
    timestamp: str = ""
    property_comuna: str = ""
    property_superficie: float = 0.0

    def __post_init__(self):
        from datetime import datetime
        self.timestamp = datetime.now().isoformat()


# =============================================================================
# CÁLCULOS GEOGRÁFICOS
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcular distancia entre dos puntos usando la fórmula de Haversine.

    Args:
        lat1, lon1: Coordenadas del punto 1
        lat2, lon2: Coordenadas del punto 2

    Returns:
        Distancia en metros
    """
    R = 6371000  # Radio de la Tierra en metros

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# =============================================================================
# LOCATION ANALYZER
# =============================================================================

class LocationAnalyzer:
    """
    Analizador de ubicación y conectividad con Metro de Santiago.

    Utiliza las coordenadas de las estaciones de Metro para calcular
    la distancia a la estación más cercana y evaluar el nivel de conectividad.
    """

    # Coordenadas aproximadas de comunas principales de Santiago (centro geográfico)
    COMMUNE_COORDINATES: Dict[str, Tuple[float, float]] = {
        "Las Condes": (-33.4170, -70.5875),
        "Vitacura": (-33.3970, -70.5780),
        "Lo Barnechea": (-33.3550, -70.5180),
        "Providencia": (-33.4270, -70.6100),
        "Ñuñoa": (-33.4560, -70.5970),
        "La Reina": (-33.4520, -70.5420),
        "Santiago": (-33.4450, -70.6550),
        "Independencia": (-33.4170, -70.6650),
        "Recoleta": (-33.4050, -70.6420),
        "San Miguel": (-33.4970, -70.6520),
        "La Florida": (-33.5220, -70.5980),
        "Maipú": (-33.5100, -70.7570),
        "Puente Alto": (-33.6100, -70.5770),
        "Peñalolén": (-33.4870, -70.5310),
        "Macul": (-33.4890, -70.6000),
        "San Joaquín": (-33.4960, -70.6300),
        "La Granja": (-33.5380, -70.6240),
        "La Cisterna": (-33.5350, -70.6600),
        "Estación Central": (-33.4520, -70.6800),
        "Quinta Normal": (-33.4400, -70.6950),
        "Cerrillos": (-33.4900, -70.7150),
        "Huechuraba": (-33.3700, -70.6350),
        "Conchalí": (-33.3900, -70.6650),
        "Quilicura": (-33.3650, -70.7250),
        "Pudahuel": (-33.4350, -70.7450),
        "Renca": (-33.4050, -70.7200),
        "El Bosque": (-33.5580, -70.6730),
        "San Bernardo": (-33.5950, -70.7000),
        "La Pintana": (-33.5850, -70.6350),
        "San Ramón": (-33.5380, -70.6420),
        "Lo Prado": (-33.4450, -70.7150),
        "Cerro Navia": (-33.4270, -70.7350),
        "Colina": (-33.2050, -70.6750),
    }

    def __init__(self, metro_stations: List[Dict[str, Any]] = None):
        """
        Inicializar analizador con estaciones de Metro.

        Args:
            metro_stations: Lista de estaciones. Si es None, usa las predefinidas.
        """
        self.stations = metro_stations or METRO_STATIONS

    def get_coordinates_for_comuna(self, comuna: str) -> Optional[Tuple[float, float]]:
        """
        Obtener coordenadas aproximadas para una comuna.

        Args:
            comuna: Nombre de la comuna

        Returns:
            Tupla (lat, lon) o None si no se encuentra
        """
        # Buscar coincidencia exacta
        if comuna in self.COMMUNE_COORDINATES:
            return self.COMMUNE_COORDINATES[comuna]

        # Buscar coincidencia parcial
        comuna_lower = comuna.lower()
        for comm, coords in self.COMMUNE_COORDINATES.items():
            if comm.lower() in comuna_lower or comuna_lower in comm.lower():
                return coords

        return None

    def analyze(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        comuna: Optional[str] = None
    ) -> LocationAnalysisResult:
        """
        Analizar ubicación y calcular conectividad con Metro.

        Args:
            lat, lon: Coordenadas de la propiedad
            comuna: Nombre de la comuna (usado si no hay coordenadas)

        Returns:
            LocationAnalysisResult con análisis completo
        """
        # Obtener coordenadas
        if lat is None or lon is None:
            if comuna:
                coords = self.get_coordinates_for_comuna(comuna)
                if coords:
                    lat, lon = coords
                else:
                    # No hay coordenadas disponibles
                    return LocationAnalysisResult(
                        nearest_station=None,
                        distance_meters=float('inf'),
                        connectivity_level=ConnectivityLevel.NONE,
                        nearby_stations=[],
                        metro_lines_nearby=[],
                        walking_time_minutes=0,
                        has_metro_access=False,
                    )
            else:
                return LocationAnalysisResult(
                    nearest_station=None,
                    distance_meters=float('inf'),
                    connectivity_level=ConnectivityLevel.NONE,
                    nearby_stations=[],
                    metro_lines_nearby=[],
                    walking_time_minutes=0,
                    has_metro_access=False,
                )

        # Calcular distancia a todas las estaciones
        stations_with_distance = []
        for station_data in self.stations:
            distance = haversine_distance(
                lat, lon,
                station_data["lat"], station_data["lon"]
            )
            station = MetroStation(
                name=station_data["name"],
                line=station_data["line"],
                lat=station_data["lat"],
                lon=station_data["lon"],
                distance_m=distance
            )
            stations_with_distance.append(station)

        # Ordenar por distancia
        stations_with_distance.sort(key=lambda s: s.distance_m)

        # Estación más cercana
        nearest = stations_with_distance[0] if stations_with_distance else None
        distance = nearest.distance_m if nearest else float('inf')

        # Determinar nivel de conectividad
        if distance < 500:
            connectivity = ConnectivityLevel.HIGH
        elif distance < 800:
            connectivity = ConnectivityLevel.MEDIUM
        elif distance < 1500:
            connectivity = ConnectivityLevel.LOW
        else:
            connectivity = ConnectivityLevel.NONE

        # Estaciones cercanas (dentro de 1.5km)
        nearby = [s for s in stations_with_distance if s.distance_m <= 1500]

        # Líneas de Metro accesibles
        lines = list(set(s.line for s in nearby))
        lines.sort()

        # Tiempo caminando (estimación: 80m/min = 4.8 km/h)
        walking_time = int(distance / 80) if distance < 3000 else 0

        return LocationAnalysisResult(
            nearest_station=nearest,
            distance_meters=distance,
            connectivity_level=connectivity,
            nearby_stations=nearby[:5],  # Top 5 más cercanas
            metro_lines_nearby=lines,
            walking_time_minutes=walking_time,
            has_metro_access=distance < 1500,
        )


# =============================================================================
# PRICE ANALYZER
# =============================================================================

class PriceAnalyzer:
    """
    Analizador de precios por comuna.

    Compara el precio de una propiedad con el promedio del mercado
    para determinar si es una oportunidad o está sobre precio.
    """

    def __init__(self, price_data: Dict[str, float] = None):
        """
        Inicializar con datos de precios por comuna.

        Args:
            price_data: Diccionario {comuna: uf_m2_promedio}
        """
        self.price_data = price_data or AVG_PRICE_PER_COMMUNE

    def get_commune_average(self, comuna: str) -> float:
        """
        Obtener precio promedio por m² para una comuna.

        Args:
            comuna: Nombre de la comuna

        Returns:
            Precio promedio en UF/m²
        """
        # Buscar coincidencia exacta
        if comuna in self.price_data:
            return self.price_data[comuna]

        # Buscar coincidencia parcial
        comuna_lower = comuna.lower()
        for comm, price in self.price_data.items():
            if comm.lower() in comuna_lower or comuna_lower in comm.lower():
                return price

        # Default
        return self.price_data.get("_default", 50.0)

    def analyze(
        self,
        precio_uf: float,
        superficie_m2: float,
        comuna: str
    ) -> PriceAnalysisResult:
        """
        Analizar precio de una propiedad.

        Args:
            precio_uf: Precio de venta en UF
            superficie_m2: Superficie en m²
            comuna: Nombre de la comuna

        Returns:
            PriceAnalysisResult con análisis completo
        """
        if superficie_m2 <= 0:
            superficie_m2 = 1  # Evitar división por cero

        # Calcular UF/m²
        uf_m2 = precio_uf / superficie_m2

        # Obtener promedio de la comuna
        commune_avg = self.get_commune_average(comuna)

        # Calcular diferencia
        diff_uf = uf_m2 - commune_avg
        diff_percent = ((uf_m2 / commune_avg) - 1) * 100 if commune_avg > 0 else 0

        # Determinar posición
        if diff_percent < -15:
            position = PricePosition.BELOW_MARKET
            is_opportunity = True
            analysis = (
                f"Esta propiedad está un {abs(diff_percent):.1f}% por debajo del promedio "
                f"de {comuna} ({commune_avg:.0f} UF/m²). Podría ser una buena oportunidad "
                f"de inversión si no hay problemas estructurales o legales."
            )
        elif diff_percent < -5:
            position = PricePosition.BELOW_MARKET
            is_opportunity = True
            analysis = (
                f"Precio ligeramente bajo el mercado ({abs(diff_percent):.1f}% menos). "
                f"Investiga las razones, pero podría ser una oportunidad."
            )
        elif diff_percent <= 10:
            position = PricePosition.AT_MARKET
            is_opportunity = False
            analysis = (
                f"El precio está alineado con el mercado de {comuna}. "
                f"Es un precio justo para la zona."
            )
        elif diff_percent <= 25:
            position = PricePosition.ABOVE_MARKET
            is_opportunity = False
            analysis = (
                f"Esta propiedad está un {diff_percent:.1f}% sobre el promedio de {comuna}. "
                f"Verifica si hay factores que justifiquen el premium (vista, piso alto, etc.)."
            )
        else:
            position = PricePosition.PREMIUM
            is_opportunity = False
            analysis = (
                f"Precio premium significativamente sobre el mercado ({diff_percent:.1f}% más). "
                f"Solo justificable si tiene características excepcionales."
            )

        return PriceAnalysisResult(
            uf_per_m2=uf_m2,
            commune_average_uf_m2=commune_avg,
            price_position=position,
            price_diff_percent=diff_percent,
            price_diff_uf_m2=diff_uf,
            is_opportunity=is_opportunity,
            analysis_text=analysis,
        )


# =============================================================================
# MARKET COMPARABLES SCRAPER
# =============================================================================

class MarketCompScraper:
    """
    Scraper de arriendos comparables.

    Busca propiedades similares en arriendo para estimar
    el precio de mercado del arriendo.
    """

    def __init__(self, rent_data: Dict[str, Tuple[float, float]] = None):
        """
        Inicializar con datos de referencia.

        Args:
            rent_data: Datos de rango de arriendos por comuna
        """
        self.rent_data = rent_data or AVG_RENT_PER_COMMUNE

    def _generate_synthetic_comparables(
        self,
        comuna: str,
        superficie_m2: float,
        dormitorios: int,
        n_samples: int = 10
    ) -> List[RentComparable]:
        """
        Generar comparables sintéticos basados en datos de mercado.

        Usado cuando el scraping real no está disponible.
        """
        # Obtener rango de precios para la comuna
        rent_range = self.rent_data.get(comuna, self.rent_data["_default"])
        min_price_m2, max_price_m2 = rent_range

        comparables = []
        random.seed(42)  # Para reproducibilidad

        for i in range(n_samples):
            # Variar superficie ±15%
            sup_factor = random.uniform(0.85, 1.15)
            sup = superficie_m2 * sup_factor

            # Calcular precio base por m²
            price_m2 = random.uniform(min_price_m2, max_price_m2)

            # Ajustar por tamaño (deptos más grandes tienen menor precio por m²)
            if sup > 100:
                price_m2 *= 0.92
            elif sup < 50:
                price_m2 *= 1.05

            # Ajustar por dormitorios
            dorm_adjust = 1 + (dormitorios - 2) * 0.03
            price_m2 *= dorm_adjust

            precio_total = price_m2 * sup

            comparable = RentComparable(
                precio_clp=round(precio_total, -3),  # Redondear a miles
                superficie_m2=round(sup, 1),
                comuna=comuna,
                dormitorios=dormitorios + random.choice([-1, 0, 0, 1]),
                banos=max(1, dormitorios + random.choice([-1, 0])),
                url=None,
            )
            comparables.append(comparable)

        return comparables

    def _remove_outliers(
        self,
        comparables: List[RentComparable],
        std_factor: float = 2.0
    ) -> List[RentComparable]:
        """
        Eliminar outliers usando desviación estándar.

        Args:
            comparables: Lista de comparables
            std_factor: Factor de desviación estándar para corte

        Returns:
            Lista filtrada sin outliers
        """
        if len(comparables) < 3:
            return comparables

        prices = [c.precio_clp for c in comparables]
        avg = mean(prices)
        std = stdev(prices) if len(prices) > 1 else 0

        if std == 0:
            return comparables

        lower_bound = avg - (std * std_factor)
        upper_bound = avg + (std * std_factor)

        return [c for c in comparables if lower_bound <= c.precio_clp <= upper_bound]

    def analyze_market_rent(
        self,
        comuna: str,
        superficie_m2: float,
        dormitorios: int,
        banos: int = 1,
        use_scraping: bool = False
    ) -> MarketRentAnalysis:
        """
        Analizar arriendos de mercado para una propiedad.

        Args:
            comuna: Comuna de la propiedad
            superficie_m2: Superficie en m²
            dormitorios: Número de dormitorios
            banos: Número de baños
            use_scraping: Intentar scraping real (puede fallar)

        Returns:
            MarketRentAnalysis con análisis completo
        """
        comparables = []
        methodology = "Estimación basada en datos de mercado"

        # Por ahora usamos datos sintéticos
        # TODO: Implementar scraping real de MercadoLibre cuando esté disponible
        if use_scraping:
            logger.warning("Scraping de comparables no implementado. Usando datos sintéticos.")

        # Generar comparables sintéticos
        comparables = self._generate_synthetic_comparables(
            comuna=comuna,
            superficie_m2=superficie_m2,
            dormitorios=dormitorios,
            n_samples=15
        )
        methodology = f"Estimación basada en rangos de mercado para {comuna} y propiedades similares"

        # Eliminar outliers
        filtered = self._remove_outliers(comparables)

        if not filtered:
            filtered = comparables  # Usar todos si el filtro eliminó todo

        # Calcular estadísticas
        prices = [c.precio_clp for c in filtered]
        prices_m2 = [c.precio_m2 for c in filtered]

        avg_rent = mean(prices)
        med_rent = median(prices)
        min_rent = min(prices)
        max_rent = max(prices)
        std_rent = stdev(prices) if len(prices) > 1 else 0
        avg_m2 = mean(prices_m2) if prices_m2 else 0

        # Sugerencia conservadora (mediana - 5%)
        suggested = med_rent * 0.95
        suggested_range = (med_rent * 0.90, med_rent * 1.05)

        return MarketRentAnalysis(
            comparables_count=len(filtered),
            average_rent_clp=round(avg_rent, 0),
            median_rent_clp=round(med_rent, 0),
            min_rent_clp=round(min_rent, 0),
            max_rent_clp=round(max_rent, 0),
            std_dev_clp=round(std_rent, 0),
            average_price_m2=round(avg_m2, 0),
            suggested_rent_clp=round(suggested, -3),  # Redondear a miles
            suggested_rent_range=(round(suggested_range[0], -3), round(suggested_range[1], -3)),
            comparables=filtered,
            methodology=methodology,
        )


# =============================================================================
# CLASE PRINCIPAL DE INTELIGENCIA DE MERCADO
# =============================================================================

class MarketIntelligence:
    """
    Clase principal que orquesta todos los análisis de mercado.

    Proporciona un reporte completo de inteligencia de mercado
    para una propiedad inmobiliaria.
    """

    def __init__(self):
        self.location_analyzer = LocationAnalyzer()
        self.price_analyzer = PriceAnalyzer()
        self.rent_analyzer = MarketCompScraper()

    def generate_report(
        self,
        precio_uf: float,
        superficie_m2: float,
        comuna: str,
        dormitorios: int = 2,
        banos: int = 1,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> MarketIntelligenceReport:
        """
        Generar reporte completo de inteligencia de mercado.

        Args:
            precio_uf: Precio de venta en UF
            superficie_m2: Superficie en m²
            comuna: Nombre de la comuna
            dormitorios: Número de dormitorios
            banos: Número de baños
            lat, lon: Coordenadas (opcional)

        Returns:
            MarketIntelligenceReport con análisis completo
        """
        # 1. Análisis de arriendos comparables
        rent_analysis = self.rent_analyzer.analyze_market_rent(
            comuna=comuna,
            superficie_m2=superficie_m2,
            dormitorios=dormitorios,
            banos=banos,
        )

        # 2. Análisis de ubicación
        location_analysis = self.location_analyzer.analyze(
            lat=lat,
            lon=lon,
            comuna=comuna,
        )

        # 3. Análisis de precio
        price_analysis = self.price_analyzer.analyze(
            precio_uf=precio_uf,
            superficie_m2=superficie_m2,
            comuna=comuna,
        )

        return MarketIntelligenceReport(
            rent_analysis=rent_analysis,
            location_analysis=location_analysis,
            price_analysis=price_analysis,
            property_comuna=comuna,
            property_superficie=superficie_m2,
        )


# =============================================================================
# EJEMPLO DE USO
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Market Intelligence Module - Chile Real Estate")
    print("=" * 70)

    # Crear instancia
    mi = MarketIntelligence()

    # Propiedad de ejemplo
    print("\n📍 Analizando propiedad en Las Condes...")
    print("   - Precio: 5,800 UF")
    print("   - Superficie: 72 m²")
    print("   - 2 dormitorios, 2 baños")

    report = mi.generate_report(
        precio_uf=5800,
        superficie_m2=72,
        comuna="Las Condes",
        dormitorios=2,
        banos=2,
    )

    # Mostrar resultados
    print("\n" + "=" * 70)
    print("📊 ANÁLISIS DE ARRIENDO")
    print("=" * 70)
    rent = report.rent_analysis
    print(f"   Comparables analizados: {rent.comparables_count}")
    print(f"   Arriendo promedio: ${rent.average_rent_clp:,.0f} CLP")
    print(f"   Arriendo mediano: ${rent.median_rent_clp:,.0f} CLP")
    print(f"   Rango: ${rent.min_rent_clp:,.0f} - ${rent.max_rent_clp:,.0f} CLP")
    print(f"   💡 Sugerido: ${rent.suggested_rent_clp:,.0f} CLP")
    print(f"   Precio por m²: ${rent.average_price_m2:,.0f} CLP/m²")

    print("\n" + "=" * 70)
    print("🚇 ANÁLISIS DE CONECTIVIDAD")
    print("=" * 70)
    loc = report.location_analysis
    if loc.nearest_station:
        print(f"   Estación más cercana: {loc.nearest_station.name} ({loc.nearest_station.line})")
        print(f"   Distancia: {loc.distance_meters:.0f} metros")
        print(f"   Tiempo caminando: ~{loc.walking_time_minutes} minutos")
        print(f"   Nivel: {loc.connectivity_level.value}")
        print(f"   Líneas accesibles: {', '.join(loc.metro_lines_nearby)}")

        if loc.connectivity_level == ConnectivityLevel.HIGH:
            print("\n   🟢 ALTA CONECTIVIDAD - Excelente ubicación")
        elif loc.connectivity_level == ConnectivityLevel.MEDIUM:
            print("\n   🟡 MEDIA CONECTIVIDAD - Buena ubicación")
    else:
        print("   ⚠️ No se encontró Metro cercano")

    print("\n" + "=" * 70)
    print("💰 ANÁLISIS DE PRECIO")
    print("=" * 70)
    price = report.price_analysis
    print(f"   UF/m² propiedad: {price.uf_per_m2:.2f}")
    print(f"   UF/m² promedio comuna: {price.commune_average_uf_m2:.2f}")
    print(f"   Diferencia: {price.price_diff_percent:+.1f}%")
    print(f"   Posición: {price.price_position.value}")

    if price.is_opportunity:
        print("\n   🟢 OPORTUNIDAD DE INVERSIÓN")
    elif price.price_position == PricePosition.ABOVE_MARKET:
        print("\n   🟡 PRECIO SOBRE MERCADO")
    elif price.price_position == PricePosition.PREMIUM:
        print("\n   🔴 PRECIO PREMIUM")

    print(f"\n   📝 {price.analysis_text}")

    print("\n" + "=" * 70)
