"""
Electrical & UPS System Engineering Module
供配电与UPS系统工程模块

This module provides power loss calculations for the electrical distribution system
in a data center, including:
- UPS efficiency modeling with load-dependent nonlinear efficiency curve
- Transformer losses (load-proportional)
- PDU distribution losses
- Redundancy considerations (simplified)

该模块为数据中心供配电系统提供功率损耗计算，包括：
- 带有负载依赖的非线性效率曲线的UPS建模
- 变压器损耗（与负载成正比）
- PDU配电损耗
- 冗余架构的简化处理
"""

import math
from typing import Tuple, Dict, Optional

# Default loss factors (can be adjusted by user)
DEFAULT_PDU_LOSS_FACTOR = 0.01      # 1% loss in PDU
DEFAULT_TRANSFORMER_LOSS_FACTOR = 0.02  # 2% loss in transformer
DEFAULT_UPS_NOMINAL_EFFICIENCY = 0.94   # 94% efficiency at rated load
DEFAULT_UPS_RATED_KW = 500.0        # Default UPS rating 500 kW

# Coefficients for UPS efficiency quadratic curve: eff = a + b*PLR + c*PLR^2
# Chosen to approximate typical double-conversion online UPS efficiency:
#   PLR=0.2 -> eff~0.90, PLR=0.5 -> eff~0.94, PLR=1.0 -> eff~0.94
UPS_EFF_COEFF = {
    'a': 0.84,   # constant term
    'b': 0.20,   # linear term
    'c': -0.10   # quadratic term
}


def calculate_pdu_loss(power_in_kw: float, loss_factor: float = DEFAULT_PDU_LOSS_FACTOR) -> Tuple[float, float]:
    """
    Calculate PDU power loss.
    Assumes loss is a fraction of input power.

    Args:
        power_in_kw: Input power to PDU (kW)
        loss_factor: Fraction of input power lost (default 0.01 = 1%)

    Returns:
        Tuple of (power_out_kw, power_loss_kw)
    """
    if power_in_kw < 0:
        raise ValueError("Input power cannot be negative.")
    if not 0 <= loss_factor < 1:
        raise ValueError("Loss factor must be between 0 and 1.")

    power_loss_kw = power_in_kw * loss_factor
    power_out_kw = power_in_kw - power_loss_kw
    return power_out_kw, power_loss_kw


def calculate_transformer_loss(power_in_kw: float, loss_factor: float = DEFAULT_TRANSFORMER_LOSS_FACTOR) -> Tuple[float, float]:
    """
    Calculate transformer power loss.
    Assumes loss is a fraction of input power (simplified model).

    Args:
        power_in_kw: Input power to transformer (kW)
        loss_factor: Fraction of input power lost (default 0.02 = 2%)

    Returns:
        Tuple of (power_out_kw, power_loss_kw)
    """
    if power_in_kw < 0:
        raise ValueError("Input power cannot be negative.")
    if not 0 <= loss_factor < 1:
        raise ValueError("Loss factor must be between 0 and 1.")

    power_loss_kw = power_in_kw * loss_factor
    power_out_kw = power_in_kw - power_loss_kw
    return power_out_kw, power_loss_kw


def calculate_ups_efficiency(plr: float, nominal_efficiency: float = DEFAULT_UPS_NOMINAL_EFFICIENCY) -> float:
    """
    Calculate UPS efficiency based on part load ratio (PLR) using a quadratic curve.
    The curve is normalized to match nominal_efficiency at PLR=1.0.

    Args:
        plr: Part load ratio (0 to 2.0, where 1.0 is full load)
        nominal_efficiency: Efficiency at rated load (PLR=1.0)

    Returns:
        Efficiency as a fraction (0 to 1)
    """
    if plr < 0:
        plr = 0.0
    # Limit PLR to reasonable range for simulation
    plr = min(plr, 2.0)

    # Calculate base efficiency from quadratic curve
    base_eff = (UPS_EFF_COEFF['a'] +
                UPS_EFF_COEFF['b'] * plr +
                UPS_EFF_COEFF['c'] * plr * plr)

    # Normalize so that at PLR=1.0, efficiency equals nominal_efficiency
    # First compute base efficiency at PLR=1.0
    base_eff_at_rated = (UPS_EFF_COEFF['a'] +
                         UPS_EFF_COEFF['b'] * 1.0 +
                         UPS_EFF_COEFF['c'] * 1.0)

    if base_eff_at_rated == 0:
        eff = nominal_efficiency
    else:
        eff = base_eff * (nominal_efficiency / base_eff_at_rated)

    # Ensure efficiency is within reasonable bounds
    return max(0.0, min(eff, 0.99))


def calculate_ups_loss(power_out_kw: float, ups_rated_kw: float,
                       nominal_efficiency: float = DEFAULT_UPS_NOMINAL_EFFICIENCY) -> Tuple[float, float, float]:
    """
    Calculate UPS input power and loss based on output power and load-dependent efficiency.

    Args:
        power_out_kw: UPS output power (kW)
        ups_rated_kw: UPS rated capacity (kW)
        nominal_efficiency: Efficiency at rated load (PLR=1.0)

    Returns:
        Tuple of (power_in_kw, power_loss_kw, efficiency)
    """
    if power_out_kw < 0:
        raise ValueError("Output power cannot be negative.")
    if ups_rated_kw <= 0:
        raise ValueError("UPS rated capacity must be positive.")

    # Calculate part load ratio
    plr = power_out_kw / ups_rated_kw

    # Calculate efficiency at this PLR
    efficiency = calculate_ups_efficiency(plr, nominal_efficiency)

    # Avoid division by zero
    if efficiency <= 0:
        power_in_kw = float('inf')
        power_loss_kw = float('inf')
    else:
        power_in_kw = power_out_kw / efficiency
        power_loss_kw = power_in_kw - power_out_kw

    return power_in_kw, power_loss_kw, efficiency


def calculate_electrical_chain(it_load_kw: float,
                               ups_rated_kw: float = DEFAULT_UPS_RATED_KW,
                               ups_nominal_efficiency: float = DEFAULT_UPS_NOMINAL_EFFICIENCY,
                               transformer_loss_factor: float = DEFAULT_TRANSFORMER_LOSS_FACTOR,
                               pdu_loss_factor: float = DEFAULT_PDU_LOSS_FACTOR) -> Dict[str, float]:
    """
    Calculate power losses through the entire electrical chain from utility to IT load.

    Power flow: Utility -> Transformer -> UPS -> PDU -> IT Load

    Args:
        it_load_kw: IT equipment power consumption (kW)
        ups_rated_kw: UPS rated capacity (kW)
        ups_nominal_efficiency: UPS efficiency at rated load
        transformer_loss_factor: Transformer loss fraction (input power)
        pdu_loss_factor: PDU loss fraction (input power)

    Returns:
        Dictionary containing:
        - it_load_kw: IT load (input)
        - pdu_input_kw: Power input to PDU
        - pdu_loss_kw: PDU power loss
        - pdu_output_kw: Power output from PDU (equals IT load in this model)
        - ups_input_kw: Power input to UPS
        - ups_loss_kw: UPS power loss
        - ups_output_kw: Power output from UPS (input to PDU)
        - transformer_input_kw: Power input to transformer (from utility)
        - transformer_loss_kw: Transformer power loss
        - transformer_output_kw: Power output from transformer (input to UPS)
        - total_facility_input_kw: Total power drawn from utility
        - overall_efficiency: IT load / total facility input
        - ups_plr: UPS part load ratio
        - ups_efficiency: UPS efficiency at operating point
    """
    if it_load_kw < 0:
        raise ValueError("IT load cannot be negative.")

    # Stage 1: PDU (after UPS, before IT)
    # We know output of PDU = IT load
    pdu_output_kw = it_load_kw
    pdu_input_kw, pdu_loss_kw = calculate_pdu_loss(pdu_output_kw / (1 - pdu_loss_factor), pdu_loss_factor)
    # Actually, the above is wrong: we need to solve for input given output.
    # Let's do it properly:
    # If loss_factor is fraction of input lost, then:
    #   output = input * (1 - loss_factor)
    #   => input = output / (1 - loss_factor)
    pdu_input_kw = it_load_kw / (1 - pdu_loss_factor)
    pdu_loss_kw = pdu_input_kw - it_load_kw

    # Stage 2: UPS (after transformer, before PDU)
    ups_output_kw = pdu_input_kw
    ups_input_kw, ups_loss_kw, ups_efficiency = calculate_ups_loss(ups_output_kw, ups_rated_kw, ups_nominal_efficiency)

    # Stage 3: Transformer (after utility, before UPS)
    transformer_output_kw = ups_input_kw
    transformer_input_kw, transformer_loss_kw = calculate_transformer_loss(transformer_output_kw / (1 - transformer_loss_factor), transformer_loss_factor)
    transformer_input_kw = ups_input_kw / (1 - transformer_loss_factor)
    transformer_loss_kw = transformer_input_kw - ups_input_kw

    # Total facility input power (from utility)
    total_facility_input_kw = transformer_input_kw

    # Overall efficiency (IT load / total input)
    if total_facility_input_kw > 0:
        overall_efficiency = it_load_kw / total_facility_input_kw
    else:
        overall_efficiency = 0.0

    return {
        'it_load_kw': it_load_kw,
        'pdu_input_kw': pdu_input_kw,
        'pdu_loss_kw': pdu_loss_kw,
        'pdu_output_kw': pdu_output_kw,
        'ups_input_kw': ups_input_kw,
        'ups_loss_kw': ups_loss_kw,
        'ups_output_kw': ups_output_kw,
        'ups_plr': ups_output_kw / ups_rated_kw if ups_rated_kw > 0 else 0.0,
        'ups_efficiency': ups_efficiency,
        'transformer_input_kw': transformer_input_kw,
        'transformer_loss_kw': transformer_loss_kw,
        'transformer_output_kw': transformer_output_kw,
        'total_facility_input_kw': total_facility_input_kw,
        'overall_efficiency': overall_efficiency
    }


if __name__ == "__main__":
    # Example calculation
    print("Electrical & UPS Engineering Module - Example Calculation")
    print("供配电与UPS系统工程模块 - 示例计算")
    print("-" * 60)

    # Example: 200 kW IT load
    it_load = 200.0  # kW
    ups_rated = 500.0  # kW
    ups_nom_eff = 0.94
    trans_loss = 0.02
    pdu_loss = 0.01

    results = calculate_electrical_chain(
        it_load_kw=it_load,
        ups_rated_kw=ups_rated,
        ups_nominal_efficiency=ups_nom_eff,
        transformer_loss_factor=trans_loss,
        pdu_loss_factor=pdu_loss
    )

    print(f"IT Load: {results['it_load_kw']:.2f} kW")
    print()
    print("PDU Stage:")
    print(f"Input to PDU: {results['pdu_input_kw']:.3f} kW")
    print(f"PDU Loss: {results['pdu_loss_kw']:.3f} kW")
    print(f"Output from PDU: {results['pdu_output_kw']:.3f} kW")
    print()
    print("UPS Stage:")
    print(f"Input to UPS: {results['ups_input_kw']:.3f} kW")
    print(f"UPS Loss: {results['ups_loss_kw']:.3f} kW")
    print(f"Output from UPS: {results['ups_output_kw']:.3f} kW")
    print(f"UPS PLR: {results['ups_plr']:.3f}")
    print(f"UPS Efficiency: {results['ups_efficiency']:.3f}")
    print()
    print("Transformer Stage:")
    print(f"Input to Transformer: {results['transformer_input_kw']:.3f} kW")
    print(f"Transformer Loss: {results['transformer_loss_kw']:.3f} kW")
    print(f"Output from Transformer: {results['transformer_output_kw']:.3f} kW")
    print()
    print("Overall System:")
    print(f"Total Facility Input Power: {results['total_facility_input_kw']:.3f} kW")
    print(f"Overall Efficiency (IT Load / Total Input): {results['overall_efficiency']:.3f}")
    print(f"Overall PUE (Total Input / IT Load): {1/results['overall_efficiency'] if results['overall_efficiency']>0 else float('inf'):.3f}")