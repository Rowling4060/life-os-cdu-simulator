"""
Chiller Plant Thermal Engineering Module
冷源系统热力学工程模块

This module provides thermodynamic calculations for a chiller plant in liquid cooling data centers, including:
- Chiller power consumption model
- Cooling tower power consumption model
- Primary and condenser pump power models
- COP calculation based on part load ratio and condenser temperature

该模块为数据中心液冷系统中的冷源系统提供热力学计算，
包括：
- 冷水机组功耗模型
- 冷却塔功耗模型
- 一次泵和冷却水泵功耗模型
- 基于负荷比和冷凝温度的COP计算
"""

import math
from typing import Tuple, Dict, Optional

# Chiller performance coefficients (simplified quadratic model for PLR effect)
# These coefficients are illustrative and should be replaced with manufacturer data
PLR_COEFFICIENTS = {
    'a0': 0.002,   # Constant term
    'a1': 0.012,   # Linear term
    'a2': 0.986    # Quadratic term
}

# Condenser temperature effect coefficients (simplified linear model)
CONDENSER_TEMP_COEFFICIENT = -0.006  # COP decreases by 0.6% per °C increase in condenser temp above rated
RATED_CONDENSING_TEMP_C = 30.0       # Rated condenser entering water temperature (°C)
RATED_EVAPORATING_TEMP_C = 7.0       # Rated evaporator leaving water temperature (°C)
RATED_COP = 5.5                      # Rated COP at standard conditions

# Cooling tower approach temperature (°C) - difference between wet bulb and condenser water temp
TOWER_APPROACH_C = 4.0
# Cooling tower range (°C) - difference between condenser water inlet and outlet
TOWER_RANGE_C = 5.0
# Cooling tower fan efficiency
TOWER_FAN_EFFICIENCY = 0.6
# Cooling tower pump efficiency
TOWER_PUMP_EFFICIENCY = 0.7

# Water properties for calculations
WATER_SPECIFIC_HEAT = 4.18  # kJ/(kg·K)
WATER_DENSITY = 1000        # kg/m³


def calculate_wet_bulb_temperature(db_temp_c: float, rh_percent: float = 50.0) -> float:
    """
    Estimate wet bulb temperature from dry bulb and relative humidity.
    Using simplified Stull's equation.

    Args:
        db_temp_c: Dry bulb temperature in °C
        rh_percent: Relative humidity in percent (default 50%)

    Returns:
        Wet bulb temperature in °C
    """
    # Simplified Stull's equation for wet bulb temperature
    wb_temp_c = db_temp_c * math.atan(0.151977 * math.pow(rh_percent + 8.313659, 0.5)) \
                + math.atan(db_temp_c + rh_percent) \
                - math.atan(rh_percent - 1.676331) \
                + 0.00391838 * math.pow(rh_percent, 1.5) * math.atan(0.023101 * rh_percent) \
                - 4.686035
    return wb_temp_c


def calculate_chiller_cop(plr: float, condenser_entering_temp_c: float,
                          rated_cop: float = RATED_COP) -> float:
    """
    Calculate chiller COP based on part load ratio and condenser entering temperature.

    Args:
        plr: Part load ratio (0 to 1+)
        condenser_entering_temp_c: Condenser entering water temperature in °C
        rated_cop: Rated COP at standard conditions

    Returns:
        COP of chiller at given conditions
    """
    # PLR effect on COP (quadratic model)
    plr_effect = (PLR_COEFFICIENTS['a0'] +
                  PLR_COEFFICIENTS['a1'] * plr +
                  PLR_COEFFICIENTS['a2'] * plr * plr)

    # Condenser temperature effect on COP (linear deviation from rated)
    temp_effect = 1.0 + CONDENSER_TEMP_COEFFICIENT * (condenser_entering_temp_c - RATED_CONDENSING_TEMP_C)

    # Ensure COP doesn't go unrealistically high or low
    cop = rated_cop * plr_effect * temp_effect
    return max(0.1, min(cop, 15.0))  # Reasonable bounds


def calculate_chiller_power(cooling_load_kw: float, outdoor_temp_c: float,
                            outdoor_rh_percent: float = 50.0,
                            chiller_rated_capacity_kw: float = 500.0,
                            rated_cop: float = RATED_COP) -> Dict[str, float]:
    """
    Calculate chiller power consumption based on cooling load and outdoor conditions.

    Args:
        cooling_load_kw: Cooling load in kW (equal to IT heat load)
        outdoor_temp_c: Outdoor dry bulb temperature in °C
        outdoor_rh_percent: Outdoor relative humidity in percent (default 50%)
        chiller_rated_capacity_kw: Rated chiller capacity in kW (default 500 kW)
        rated_cop: Rated COP at standard conditions

    Returns:
        Dictionary containing:
        - chiller_power_kw: Electrical power to chiller compressor
        - cop: Coefficient of performance
        - plr: Part load ratio
        - condenser_entering_temp_c: Estimated condenser entering water temperature
        - chiller_heat_rejection_kw: Heat rejected by chiller to condenser loop
    """
    # Estimate wet bulb temperature from outdoor conditions
    wet_bulb_temp_c = calculate_wet_bulb_temperature(outdoor_temp_c, outdoor_rh_percent)

    # Estimate condenser entering water temperature (wet bulb + approach)
    condenser_entering_temp_c = wet_bulb_temp_c + TOWER_APPROACH_C

    # Calculate part load ratio (clamp to reasonable range)
    plr = cooling_load_kw / chiller_rated_capacity_kw
    plr = max(0.0, min(plr, 2.0))  # Allow overload up to 200% for simulation

    # Calculate COP at current conditions
    cop = calculate_chiller_cop(plr, condenser_entering_temp_c, rated_cop)

    # Calculate chiller electrical power
    if cop <= 0:
        chiller_power_kw = float('inf')
    else:
        chiller_power_kw = cooling_load_kw / cop

    # Calculate heat rejection to condenser loop (cooling load + compressor power)
    chiller_heat_rejection_kw = cooling_load_kw + chiller_power_kw

    return {
        'chiller_power_kw': chiller_power_kw,
        'cop': cop,
        'plr': plr,
        'condenser_entering_temp_c': condenser_entering_temp_c,
        'chiller_heat_rejection_kw': chiller_heat_rejection_kw
    }


def calculate_cooling_tower_power(chiller_heat_rejection_kw: float,
                                  outdoor_temp_c: float,
                                  outdoor_rh_percent: float = 50.0) -> Dict[str, float]:
    """
    Calculate cooling tower power consumption (fan and pump).

    Args:
        chiller_heat_rejection_kw: Heat rejected by chiller to condenser loop (kW)
        outdoor_temp_c: Outdoor dry bulb temperature in °C
        outdoor_rh_percent: Outdoor relative humidity in percent (default 50%)

    Returns:
        Dictionary containing:
        - tower_fan_power_kw: Cooling tower fan power
        - tower_pump_power_kw: Cooling tower pump power
        - condenser_water_flow_l_s: Condenser water flow rate
        - condenser_leaving_temp_c: Condenser leaving water temperature
    """
    # Estimate wet bulb temperature
    wet_bulb_temp_c = calculate_wet_bulb_temperature(outdoor_temp_c, outdoor_rh_percent)

    # Condenser entering water temperature (from chiller)
    condenser_entering_temp_c = wet_bulb_temp_c + TOWER_APPROACH_C

    # Condenser leaving water temperature (entering + range)
    condenser_leaving_temp_c = condenser_entering_temp_c + TOWER_RANGE_C

    # Calculate condenser water flow rate based on heat rejection and range
    # Q = m_dot * c * ΔT  =>  m_dot = Q / (c * ΔT)
    # Volumetric flow rate L/s = (Q_kW * 1000) / (c_kJ/(kg·K) * ΔT_K * density_kg/m³) * 1000?
    # Actually: m_dot_kg/s = Q_kW / (c_kJ/(kg·K) * ΔT_K)
    #          V_dot_L/s = m_dot_kg/s / density_kg/m³ * 1000
    delta_t_c = TOWER_RANGE_C
    if delta_t_c <= 0:
        condenser_water_flow_l_s = 0.0
    else:
        mass_flow_kg_s = chiller_heat_rejection_kw / (WATER_SPECIFIC_HEAT * delta_t_c)
        condenser_water_flow_l_s = (mass_flow_kg_s / WATER_DENSITY) * 1000

    # Calculate tower fan power (simplified: proportional to heat rejection and approach)
    # Actual fan power depends on airflow, which depends on range and wet bulb
    # We use a simplified model: fan power = k * heat_rejection * (approach / range)
    fan_power_factor = 0.01  # kW per kW of heat rejection (adjustable)
    tower_fan_power_kw = chiller_heat_rejection_kw * fan_power_factor * (TOWER_APPROACH_C / TOWER_RANGE_C)

    # Calculate tower pump power (for pumping water to tower height)
    # Simplified: assume 10m head, flow rate as above
    pump_head_m = 10.0  # meters
    # Hydraulic power = (flow_rate_m3/s * head_m * gravity * density) / efficiency
    # flow_rate_m3/s = condenser_water_flow_l_s / 1000
    # gravity = 9.81 m/s²
    # density = WATER_DENSITY kg/m³
    if condenser_water_flow_l_s > 0:
        flow_rate_m3_s = condenser_water_flow_l_s / 1000
        hydraulic_power_w = flow_rate_m3_s * pump_head_m * 9.81 * WATER_DENSITY
        tower_pump_power_w = hydraulic_power_w / TOWER_PUMP_EFFICIENCY
        tower_pump_power_kw = tower_pump_power_w / 1000
    else:
        tower_pump_power_kw = 0.0

    return {
        'tower_fan_power_kw': tower_fan_power_kw,
        'tower_pump_power_kw': tower_pump_power_kw,
        'condenser_water_flow_l_s': condenser_water_flow_l_s,
        'condenser_leaving_temp_c': condenser_leaving_temp_c,
        'condenser_entering_temp_c': condenser_entering_temp_c
    }


def calculate_primary_pump_power(evaporator_heat_kw: float,
                                 evaporator_delta_t_c: float = 5.0,
                                 pressure_drop_bar: float = 1.5,
                                 pump_efficiency: float = 0.7) -> Dict[str, float]:
    """
    Calculate primary pump power for chiller evaporator loop (between chiller and CDU).

    Args:
        evaporator_heat_kw: Heat absorbed by chiller evaporator (kW) ≈ cooling load
        evaporator_delta_t_c: Temperature difference across evaporator (°C)
        pressure_drop_bar: Pressure drop across primary loop (bar)
        pump_efficiency: Pump efficiency (0-1)

    Returns:
        Dictionary containing:
        - primary_pump_power_kw: Primary pump electrical power
        - primary_flow_l_s: Primary loop flow rate
    """
    # Calculate primary loop flow rate based on evaporator heat and ΔT
    if evaporator_delta_t_c <= 0:
        primary_flow_l_s = 0.0
    else:
        # Q = m_dot * c * ΔT
        mass_flow_kg_s = evaporator_heat_kw / (WATER_SPECIFIC_HEAT * evaporator_delta_t_c)
        primary_flow_l_s = (mass_flow_kg_s / WATER_DENSITY) * 1000

    # Calculate pump power using same function as in thermal_engine (but we'll inline to avoid import)
    # Convert flow rate to m³/s
    flow_rate_m3_s = primary_flow_l_s * 0.001
    # Convert pressure drop to Pa
    pressure_drop_pa = pressure_drop_bar * 100000
    # Hydraulic power: P_hyd = Q * Δp (Watts)
    hydraulic_power_w = flow_rate_m3_s * pressure_drop_pa
    # Shaft power: P_shaft = P_hyd / η
    shaft_power_w = hydraulic_power_w / pump_efficiency
    # Convert to kW
    primary_pump_power_kw = shaft_power_w / 1000

    return {
        'primary_pump_power_kw': primary_pump_power_kw,
        'primary_flow_l_s': primary_flow_l_s
    }


def calculate_chiller_plant_total_power(it_power_kw: float, outdoor_temp_c: float,
                                        outdoor_rh_percent: float = 50.0,
                                        chiller_rated_capacity_kw: float = 500.0,
                                        rated_cop: float = RATED_COP) -> Dict[str, float]:
    """
    Calculate total chiller plant power consumption.

    Args:
        it_power_kw: IT equipment power in kW (equal to cooling load)
        outdoor_temp_c: Outdoor dry bulb temperature in °C
        outdoor_rh_percent: Outdoor relative humidity in percent (default 50%)
        chiller_rated_capacity_kw: Rated chiller capacity in kW (default 500 kW)
        rated_cop: Rated COP at standard conditions

    Returns:
        Dictionary containing all power components and efficiency metrics
    """
    # Calculate chiller power
    chiller_results = calculate_chiller_power(
        cooling_load_kw=it_power_kw,
        outdoor_temp_c=outdoor_temp_c,
        outdoor_rh_percent=outdoor_rh_percent,
        chiller_rated_capacity_kw=chiller_rated_capacity_kw,
        rated_cop=rated_cop
    )

    # Calculate cooling tower power
    tower_results = calculate_cooling_tower_power(
        chiller_heat_rejection_kw=chiller_results['chiller_heat_rejection_kw'],
        outdoor_temp_c=outdoor_temp_c,
        outdoor_rh_percent=outdoor_rh_percent
    )

    # Calculate primary pump power (evaporator loop)
    pump_results = calculate_primary_pump_power(
        evaporator_heat_kw=it_power_kw,  # Approximately equal to cooling load
        evaporator_delta_t_c=5.0,        # Typical evaporator ΔT
        pressure_drop_bar=1.5,
        pump_efficiency=0.7
    )

    # Sum up all power components
    chiller_power_kw = chiller_results['chiller_power_kw']
    tower_fan_power_kw = tower_results['tower_fan_power_kw']
    tower_pump_power_kw = tower_results['tower_pump_power_kw']
    primary_pump_power_kw = pump_results['primary_pump_power_kw']

    total_chiller_plant_power_kw = (chiller_power_kw +
                                   tower_fan_power_kw +
                                   tower_pump_power_kw +
                                   primary_pump_power_kw)

    # Overall plant COP (cooling load / total plant power)
    if total_chiller_plant_power_kw > 0:
        plant_cop = it_power_kw / total_chiller_plant_power_kw
    else:
        plant_cop = float('inf')

    return {
        # Input parameters
        'it_power_kw': it_power_kw,
        'outdoor_temp_c': outdoor_temp_c,
        'outdoor_rh_percent': outdoor_rh_percent,

        # Chiller results
        'chiller_power_kw': chiller_power_kw,
        'chiller_cop': chiller_results['cop'],
        'plr': chiller_results['plr'],
        'condenser_entering_temp_c': chiller_results['condenser_entering_temp_c'],
        'chiller_heat_rejection_kw': chiller_results['chiller_heat_rejection_kw'],

        # Cooling tower results
        'tower_fan_power_kw': tower_fan_power_kw,
        'tower_pump_power_kw': tower_pump_power_kw,
        'condenser_water_flow_l_s': tower_results['condenser_water_flow_l_s'],
        'condenser_leaving_temp_c': tower_results['condenser_leaving_temp_c'],
        'condenser_entering_temp_c_tower': tower_results['condenser_entering_temp_c'],

        # Primary pump results
        'primary_pump_power_kw': primary_pump_power_kw,
        'primary_flow_l_s': pump_results['primary_flow_l_s'],

        # Total plant power
        'total_chiller_plant_power_kw': total_chiller_plant_power_kw,
        'plant_cop': plant_cop
    }


if __name__ == "__main__":
    # Example calculation
    print("Chiller Plant Engineering Module - Example Calculation")
    print("冷源系统热力学工程模块 - 示例计算")
    print("-" * 60)

    # Example: 200 kW IT load, 35°C outdoor temp, 60% RH
    it_power = 200.0  # kW
    outdoor_temp = 35.0  # °C
    outdoor_rh = 60.0  # %

    results = calculate_chiller_plant_total_power(
        it_power_kw=it_power,
        outdoor_temp_c=outdoor_temp,
        outdoor_rh_percent=outdoor_rh
    )

    print(f"IT Load: {results['it_power_kw']:.2f} kW")
    print(f"Outdoor Temperature: {results['outdoor_temp_c']:.1f}°C")
    print(f"Outdoor RH: {results['outdoor_rh_percent']:.1f}%")
    print()
    print("Chiller Power:")
    print(f"  Electrical Power: {results['chiller_power_kw']:.3f} kW")
    print(f"  COP: {results['chiller_cop']:.3f}")
    print(f"  PLR: {results['plr']:.3f}")
    print(f"  Condenser Entering Temp: {results['condenser_entering_temp_c']:.2f}°C")
    print(f"  Heat Rejection: {results['chiller_heat_rejection_kw']:.3f} kW")
    print()
    print("Cooling Tower:")
    print(f"  Fan Power: {results['tower_fan_power_kw']:.3f} kW")
    print(f"  Pump Power: {results['tower_pump_power_kw']:.3f} kW")
    print(f"  Condenser Water Flow: {results['condenser_water_flow_l_s']:.3f} L/s")
    print(f"  Condenser Entering Temp: {results['condenser_entering_temp_c_tower']:.2f}°C")
    print(f"  Condenser Leaving Temp: {results['condenser_leaving_temp_c']:.2f}°C")
    print()
    print("Primary Pump (Evaporator Loop):")
    print(f"  Pump Power: {results['primary_pump_power_kw']:.3f} kW")
    print(f"  Primary Flow: {results['primary_flow_l_s']:.3f} L/s")
    print()
    print("Total Chiller Plant Power: {results['total_chiller_plant_power_kw']:.3f} kW")
    print(f"Plant COP (IT Power / Plant Power): {results['plant_cop']:.3f}")