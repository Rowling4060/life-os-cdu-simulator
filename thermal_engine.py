"""
CDU Thermal Engineering Module
冷却液分配单元热力学工程模块

This module provides core thermodynamic calculations for a Coolant Distribution Unit (CDU)
in liquid cooling data centers, including:
- Heat exchange calculations
- Primary/secondary side flow calculations
- Pump and fan power consumption models
- PUE and energy efficiency metrics

该模块为数据中心液冷系统中的冷却液分配单元（CDU）提供核心热力学计算，
包括：
- 换热量计算
- 一次侧/二次侧流量计算
- 泵浦与风机功耗模型
- PUE 和能效比指标
"""

import math
from typing import Tuple, Dict, Optional

# Coolant properties database (simplified)
# 冷却液物性参数数据库（简化版）
COOLANT_PROPERTIES = {
    "water": {
        "specific_heat": 4.18,  # kJ/(kg·K)
        "density": 1000,        # kg/m³
        "viscosity": 0.001,     # Pa·s (at 20°C)
        "thermal_conductivity": 0.6,  # W/(m·K)
    },
    "eg_water_30": {  # 30% ethylene glycol / water
        "specific_heat": 3.8,   # kJ/(kg·K)
        "density": 1050,        # kg/m³
        "viscosity": 0.002,     # Pa·s
        "thermal_conductivity": 0.45, # W/(m·K)
    },
    "eg_water_50": {  # 50% ethylene glycol / water
        "specific_heat": 3.4,   # kJ/(kg·K)
        "density": 1070,        # kg/m³
        "viscosity": 0.004,     # Pa·s
        "thermal_conductivity": 0.35, # W/(m·K)
    },
    "pg_water_30": {  # 30% propylene glycol / water
        "specific_heat": 3.9,   # kJ/(kg·K)
        "density": 1040,        # kg/m³
        "viscosity": 0.0025,    # Pa·s
        "thermal_conductivity": 0.48, # W/(m·K)
    },
    "novec_7100": {  # 3M Novec 7100 dielectric fluid (two-phase)
        "specific_heat": 1.1,   # kJ/(kg·K) (approximate for liquid)
        "density": 1400,        # kg/m³
        "viscosity": 0.0006,    # Pa·s
        "thermal_conductivity": 0.07, # W/(m·K)
        "latent_heat": 85,      # kJ/kg (approximate)
        "boiling_point": 34,    # °C at 1 atm
    }
}

def get_coolant_properties(coolant_type: str) -> Dict[str, float]:
    """
    Retrieve coolant properties by type.
    根据类型获取冷却液物性参数。

    Args:
        coolant_type: String identifier for coolant (e.g., "water", "eg_water_30")

    Returns:
        Dictionary containing specific_heat, density, viscosity, thermal_conductivity
        包含比热容、密度、粘度、导热系数的字典

    Raises:
        ValueError: If coolant_type is not found
    """
    if coolant_type not in COOLANT_PROPERTIES:
        available = ", ".join(COOLANT_PROPERTIES.keys())
        raise ValueError(f"Coolant type '{coolant_type}' not found. Available: {available}")
    return COOLANT_PROPERTIES[coolant_type].copy()

def calculate_heat_load(
    it_power_kw: float,
    delta_t_k: float,
    coolant_type: str = "water",
    flow_rate_l_s: Optional[float] = None
) -> Tuple[float, float, float]:
    """
    Calculate heat load and verify flow rate sufficiency.
    计算散热负荷并验证流量是否足够。

    Args:
        it_power_kw: IT equipment power in kW
        delta_t_k: Temperature difference between supply and return in K
        coolant_type: Coolant type identifier (default: "water")
        flow_rate_l_s: Optional coolant flow rate in L/s to verify sufficiency

    Returns:
        Tuple of (heat_load_kw, required_flow_l_s, actual_flow_l_s)
        其中 actual_flow_l_s 为输入流量（如果提供）或所需流量（如果未提供）

    Formula:
        Q = m_dot * c * ΔT
        where Q = heat load (kW), m_dot = mass flow rate (kg/s),
              c = specific heat (kJ/(kg·K)), ΔT = temperature difference (K)
    """
    props = get_coolant_properties(coolant_type)
    specific_heat = props["specific_heat"]  # kJ/(kg·K)
    density = props["density"]              # kg/m³

    # Heat load equals IT power (assuming all IT power becomes heat to be removed)
    heat_load_kw = it_power_kw

    # Convert heat load to kJ/s (1 kW = 1 kJ/s)
    heat_load_kj_s = heat_load_kw

    # Calculate required mass flow rate: m_dot = Q / (c * ΔT)
    if delta_t_k <= 0:
        raise ValueError("Temperature difference (ΔT) must be positive.")
    if specific_heat <= 0:
        raise ValueError("Coolant specific heat must be positive.")

    required_mass_flow_kg_s = heat_load_kj_s / (specific_heat * delta_t_k)  # kg/s

    # Convert to volumetric flow rate: V_dot = m_dot / ρ
    required_volume_flow_m3_s = required_mass_flow_kg_s / density  # m³/s
    required_flow_l_s = required_volume_flow_m3_s * 1000           # L/s

    # If flow rate is provided, use it; otherwise use required flow
    actual_flow_l_s = flow_rate_l_s if flow_rate_l_s is not None else required_flow_l_s

    return heat_load_kw, required_flow_l_s, actual_flow_l_s

def calculate_pumping_power(
    flow_rate_l_s: float,
    pressure_drop_bar: float,
    pump_efficiency: float = 0.7
) -> float:
    """
    Calculate pumping power consumption.
    计算水泵功耗。

    Args:
        flow_rate_l_s: Coolant flow rate in L/s
        pressure_drop_bar: Pressure drop across the system in bar
        pump_efficiency: Pump efficiency (0-1, default 0.7)

    Returns:
        Pumping power in kW

    Formula:
        P = (Q * Δp) / η
        where Q = flow rate (m³/s), Δp = pressure drop (Pa), η = efficiency
        Note: 1 bar = 100,000 Pa, 1 L/s = 0.001 m³/s
    """
    if flow_rate_l_s < 0:
        raise ValueError("Flow rate cannot be negative.")
    if pressure_drop_bar < 0:
        raise ValueError("Pressure drop cannot be negative.")
    if not 0 < pump_efficiency <= 1:
        raise ValueError("Pump efficiency must be between 0 and 1 (exclusive of 0).")

    # Convert flow rate to m³/s
    flow_rate_m3_s = flow_rate_l_s * 0.001

    # Convert pressure drop to Pa
    pressure_drop_pa = pressure_drop_bar * 100000

    # Hydraulic power: P_hyd = Q * Δp (Watts)
    hydraulic_power_w = flow_rate_m3_s * pressure_drop_pa

    # Shaft power: P_shaft = P_hyd / η
    shaft_power_w = hydraulic_power_w / pump_efficiency

    # Convert to kW
    shaft_power_kw = shaft_power_w / 1000

    return shaft_power_kw

def calculate_fan_power(
    airflow_m3_h: float,
    pressure_drop_pa: float,
    fan_efficiency: float = 0.6
) -> float:
    """
    Calculate fan power consumption for air-cooled components (e.g., radiators).
    计算风机功耗（用于风冷部件如散热器）。

    Args:
        airflow_m3_h: Airflow rate in m³/h
        pressure_drop_pa: Pressure drop across the fan in Pa
        fan_efficiency: Fan efficiency (0-1, default 0.6)

    Returns:
        Fan power in kW
    """
    if airflow_m3_h < 0:
        raise ValueError("Airflow rate cannot be negative.")
    if pressure_drop_pa < 0:
        raise ValueError("Pressure drop cannot be negative.")
    if not 0 < fan_efficiency <= 1:
        raise ValueError("Fan efficiency must be between 0 and 1 (exclusive of 0).")

    # Convert airflow to m³/s
    airflow_m3_s = airflow_m3_h / 3600

    # Hydraulic power: P_hyd = Q * Δp (Watts)
    hydraulic_power_w = airflow_m3_s * pressure_drop_pa

    # Shaft power: P_shaft = P_hyd / η
    shaft_power_w = hydraulic_power_w / fan_efficiency

    # Convert to kW
    shaft_power_kw = shaft_power_w / 1000

    return shaft_power_kw

def calculate_cdu_performance(
    it_power_kw: float,
    delta_t_k: float,
    coolant_type: str = "water",
    flow_rate_l_s: Optional[float] = None,
    primary_side_delta_p_bar: float = 1.5,
    secondary_side_delta_p_bar: float = 2.0,
    pump_efficiency: float = 0.7,
    fan_power_kw: float = 0.0,
    auxiliary_other_kw: float = 0.0
) -> Dict[str, float]:
    """
    Calculate comprehensive CDU performance metrics.
    计算CDU综合性能指标。

    Args:
        it_power_kw: IT equipment power in kW
        delta_t_k: Temperature difference between supply and return in K
        coolant_type: Coolant type identifier
        flow_rate_l_s: Optional coolant flow rate in L/s (if None, calculates required)
        primary_side_delta_p_bar: Pressure drop on primary side (chiller side) in bar
        secondary_side_delta_p_bar: Pressure drop on secondary side (CDU to racks) in bar
        pump_efficiency: Pump efficiency (default 0.7)
        fan_power_kw: Fan power for air-cooled condensers/radiators in kW
        auxiliary_other_kw: Other auxiliary power (controls, lighting, etc.) in kW

    Returns:
        Dictionary containing:
        - heat_load_kw: System heat dissipation load
        - required_flow_l_s: Required coolant flow rate
        - actual_flow_l_s: Actual coolant flow rate (input or required)
        - primary_pump_power_kw: Primary side pump power
        - secondary_pump_power_kw: Secondary side pump power
        - total_pump_power_kw: Total pump power
        - total_auxiliary_kw: Total auxiliary power (pumps + fans + other)
        - total_facility_power_kw: Total facility power (IT + auxiliary)
        - pue: Power Usage Effectiveness
        - energy_efficiency_ratio: Energy Efficiency Ratio (IT power / auxiliary power)
        - coolant_type: Used coolant type
        - delta_t_k: Temperature difference
    """
    # Calculate heat load and flow rates
    heat_load_kw, required_flow_l_s, actual_flow_l_s = calculate_heat_load(
        it_power_kw, delta_t_k, coolant_type, flow_rate_l_s
    )

    # Calculate pump power for both sides
    primary_pump_power_kw = calculate_pumping_power(
        actual_flow_l_s, primary_side_delta_p_bar, pump_efficiency
    )

    secondary_pump_power_kw = calculate_pumping_power(
        actual_flow_l_s, secondary_side_delta_p_bar, pump_efficiency
    )

    total_pump_power_kw = primary_pump_power_kw + secondary_pump_power_kw

    # Total auxiliary power
    total_auxiliary_kw = total_pump_power_kw + fan_power_kw + auxiliary_other_kw

    # Total facility power
    total_facility_power_kw = it_power_kw + total_auxiliary_kw

    # PUE calculation
    if it_power_kw <= 0:
        pue = float('inf')
    else:
        pue = total_facility_power_kw / it_power_kw

    # Energy Efficiency Ratio (EER) - IT power over auxiliary power
    if total_auxiliary_kw <= 0:
        eer = float('inf')
    else:
        eer = it_power_kw / total_auxiliary_kw

    return {
        "heat_load_kw": heat_load_kw,
        "required_flow_l_s": required_flow_l_s,
        "actual_flow_l_s": actual_flow_l_s,
        "primary_pump_power_kw": primary_pump_power_kw,
        "secondary_pump_power_kw": secondary_pump_power_kw,
        "total_pump_power_kw": total_pump_power_kw,
        "total_auxiliary_kw": total_auxiliary_kw,
        "total_facility_power_kw": total_facility_power_kw,
        "pue": pue,
        "energy_efficiency_ratio": eer,
        "coolant_type": coolant_type,
        "delta_t_k": delta_t_k
    }

def format_performance_report(results: Dict[str, float]) -> str:
    """
    Format CDU performance results as a readable report.
    格式化CDU性能结果为可读报告。

    Args:
        results: Dictionary from calculate_cdu_performance

    Returns:
        Formatted string report
    """
    lines = [
        "=" * 60,
        "CDU THERMAL PERFORMANCE REPORT",
        "CDU 热力学性能报告",
        "=" * 60,
        f"IT Load: {results['it_power_kw'] if 'it_power_kw' in results else 'N/A':.2f} kW",
        f"Heat Dissipation Load: {results['heat_load_kw']:.2f} kW",
        f"Coolant Type: {results['coolant_type']}",
        f"Temperature Difference (ΔT): {results['delta_t_k']:.2f} K",
        f"Required Coolant Flow Rate: {results['required_flow_l_s']:.3f} L/s",
        f"Actual Coolant Flow Rate: {results['actual_flow_l_s']:.3f} L/s",
        "",
        "POWER CONSUMPTION BREAKDOWN / 功耗分解:",
        f"  Primary Side Pump Power: {results['primary_pump_power_kw']:.3f} kW",
        f"  Secondary Side Pump Power: {results['secondary_pump_power_kw']:.3f} kW",
        f"  Total Pump Power: {results['total_pump_power_kw']:.3f} kW",
        f"  Fan Power: {results.get('fan_power_kw', 0.0):.3f} kW",
        f"  Other Auxiliary: {results.get('auxiliary_other_kw', 0.0):.3f} kW",
        f"  Total Auxiliary Power: {results['total_auxiliary_kw']:.3f} kW",
        "",
        "EFFICIENCY METRICS / 能效指标:",
        f"  Total Facility Power: {results['total_facility_power_kw']:.3f} kW",
        f"  Power Usage Effectiveness (PUE): {results['pue']:.3f}",
        f"  Energy Efficiency Ratio (EER): {results['energy_efficiency_ratio']:.3f}",
        "=" * 60
    ]
    return "\n".join(lines)

# Example usage and testing
if __name__ == "__main__":
    # Example calculation for a 100 kW IT load with water coolant
    print("CDU Thermal Engineering Module - Example Calculation")
    print("CDU 热力学工程模块 - 示例计算")
    print("-" * 50)

    # Input parameters
    it_power = 100.0  # kW
    delta_t = 5.0     # K
    coolant = "water"

    # Calculate performance
    results = calculate_cdu_performance(
        it_power_kw=it_power,
        delta_t_k=delta_t,
        coolant_type=coolant,
        flow_rate_l_s=None,  # Let function calculate required flow
        primary_side_delta_p_bar=1.5,
        secondary_side_delta_p_bar=2.0,
        pump_efficiency=0.7,
        fan_power_kw=2.0,    # Example fan power for radiator
        auxiliary_other_kw=0.5
    )

    # Add IT power to results for reporting (not returned by function)
    results['it_power_kw'] = it_power

    # Print formatted report
    print(format_performance_report(results))