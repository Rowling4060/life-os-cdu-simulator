# Life OS v2.0 — Data Center Liquid-Cooling CDU Digital Twin

An interactive engineering simulation and digital-twin-style dashboard for exploring the thermal and electrical behavior of a liquid-cooled data center. The application brings together a coolant distribution unit (CDU), chiller plant, cooling tower, utility power chain, and live outdoor weather in one Streamlit interface.

**Life OS v2.0 数据中心液冷 CDU 数字孪生与仿真系统**<br>
面向液冷数据中心的交互式工程仿真仪表板，用于联合观察冷却液分配单元（CDU）、冷水机组、冷却塔、供配电链路与室外气象条件。通过可调参数和实时天气输入，快速分析负载、流量、功耗与能效指标之间的关系。

> **Model scope / 模型范围:** This is a transparent, parameter-driven simulation built from simplified engineering models. It is not connected to facility controls, telemetry, or equipment vendor performance maps, and is not a substitute for commissioning, equipment selection, or a safety analysis.<br>
> 本项目使用可读、可调的简化工程模型进行情景分析；它不接入现场控制系统、运行遥测或厂商性能曲线，不能替代设备选型、调试验证或安全分析。

## Highlights / 功能概览

- **Integrated facility view / 全站综合视图** — Summarizes IT load, cooling-plant consumption, electrical losses, facility input power, and overall PUE.
- **CDU thermal model / CDU 热力学模型** — Estimates heat load, coolant flow, pump and fan power, facility power, PUE, and energy-efficiency ratio.
- **Chiller plant model / 冷源系统模型** — Estimates wet-bulb temperature, chiller COP and compressor power, cooling-tower fan and pump power, primary-loop flow, and plant COP.
- **Electrical-chain model / 供配电链路模型** — Represents utility → transformer → UPS → PDU → IT load, including load-dependent UPS efficiency and configurable distribution losses.
- **Interactive sensitivity analysis / 交互式敏感性分析** — Visualizes how changing IT load, temperature difference, or outdoor conditions affects flow, power, COP, and PUE.
- **Live weather lookup / 实时天气查询** — Fetches current temperature and relative humidity from Open-Meteo without an API key. Accepts named cities, predefined locations, or latitude/longitude input.
- **Standalone calculation modules / 可独立调用的计算模块** — Core calculations can also be imported from Python or run individually for example output.

## Dashboard / 仪表板

The application provides four tabs:

| Tab | Scope |
| --- | --- |
| **Executive Summary** | Combined facility energy view, headline KPIs, and system-level trends. |
| **CDU Side** | Coolant selection, flow and pressure-drop assumptions, pump/fan power, PUE, and flow/efficiency charts. |
| **Chiller Plant Side** | Outdoor dry-bulb temperature and humidity, weather lookup, chiller/tower/pump power, COP, and temperature/load sensitivity. |
| **Electrical & UPS** | UPS rating and nominal efficiency, transformer/PDU loss factors, electrical-chain losses, and load-dependent efficiency. |

Shared simulation inputs include IT equipment power, supply/return temperature difference, coolant, automatic or manual coolant flow, pump efficiency, and auxiliary loads. The dashboard recalculates results interactively as inputs change.

仪表板包含全站综合能效、CDU、冷源系统、供配电与 UPS 四个视图。侧边栏集中设置 IT 负载、供回水温差、冷却液、流量模式、压降及辅助设备参数；冷源视图还支持查询天气或手动调整室外温湿度。

## Architecture / 模块结构

```text
app_demo.py             Streamlit UI, shared controls, charts, and system summary
thermal_engine.py       CDU heat balance, coolant flow, pump/fan power, and PUE
chiller_engine.py       Chiller COP/power, cooling tower, primary pump, and plant COP
electrical_engine.py    Transformer, UPS, and PDU losses and end-to-end power chain
weather_client.py       Open-Meteo geocoding/forecast client and city coordinates
```

### Core modules / 核心模块

#### `thermal_engine.py` — CDU thermal and hydraulic calculations

- `COOLANT_PROPERTIES` provides simplified properties for water, 30%/50% ethylene-glycol mixtures, 30% propylene-glycol mixture, and Novec 7100.
- `calculate_heat_load(...)` treats IT electrical power as the heat load and estimates required volumetric flow from `Q = ṁ × cp × ΔT`.
- `calculate_pumping_power(...)` and `calculate_fan_power(...)` estimate auxiliary power from flow, pressure drop, and efficiency.
- `calculate_cdu_performance(...)` aggregates primary/secondary pump power, other auxiliaries, facility power, PUE, and energy-efficiency ratio.
- `format_performance_report(...)` formats a human-readable summary of the calculated CDU results.

#### `chiller_engine.py` — Chiller plant and heat rejection

- `calculate_wet_bulb_temperature(...)` estimates wet-bulb temperature from outdoor dry-bulb temperature and relative humidity using a simplified Stull equation.
- `calculate_chiller_cop(...)` estimates COP from part-load ratio and condenser entering-water temperature.
- `calculate_chiller_power(...)` derives compressor power and heat rejected to the condenser loop.
- `calculate_cooling_tower_power(...)` estimates tower fan/pump power, condenser-water flow, and water temperatures.
- `calculate_primary_pump_power(...)` and `calculate_chiller_plant_total_power(...)` provide primary-loop and aggregate plant results, including plant COP.

#### `electrical_engine.py` — Facility power distribution

- Calculates PDU and transformer losses from configurable input-power loss factors.
- Models UPS efficiency as a load-dependent curve normalized to the configured rated efficiency.
- `calculate_electrical_chain(...)` works backward from IT load through PDU, UPS, and transformer to estimate utility input, stage losses, UPS part-load ratio, and overall electrical efficiency.

#### `weather_client.py` — Outdoor weather input

- `get_weather_by_city_name(...)` accepts a predefined Chinese city, another city resolved via Open-Meteo geocoding, or a `latitude, longitude` string.
- `get_live_weather(...)` retains a convenience interface for the predefined city list: Tianjin, Singapore, Frankfurt, and Ashburn.
- Both weather functions return temperature in °C and relative humidity in percent. If a lookup or request fails, the client warns and returns its configured fallback values (25 °C, 60% RH).
- Weather is fetched only when requested from the dashboard; no API key is needed.

## Quick start / 快速开始

### Requirements

- Python 3.10 or later
- Internet access for live weather lookup (the dashboard and calculation engines can otherwise run with manually supplied/default weather)

### Install and launch

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install streamlit pandas plotly numpy requests
python -m streamlit run app_demo.py
```

Streamlit prints a local URL (typically `http://localhost:8501`) in the terminal. Open it in a browser to use the dashboard. To stop the server, press `Ctrl+C` in that terminal.

Windows PowerShell 用户可在项目目录中运行上述命令。若执行策略阻止虚拟环境激活，可直接调用 `.venv\Scripts\python.exe -m pip ...` 和 `.venv\Scripts\python.exe -m streamlit run app_demo.py`。

### Run a calculation module directly

Each calculation engine includes a small example entry point:

```powershell
python thermal_engine.py
python chiller_engine.py
python electrical_engine.py
python weather_client.py
```

The weather example makes network requests. The other three commands perform local example calculations.

### Use the engines from Python

```python
from thermal_engine import calculate_cdu_performance
from chiller_engine import calculate_chiller_plant_total_power
from electrical_engine import calculate_electrical_chain

cdu = calculate_cdu_performance(
    it_power_kw=200.0,
    delta_t_k=5.0,
    coolant_type="water",
)
plant = calculate_chiller_plant_total_power(
    it_power_kw=200.0,
    outdoor_temp_c=30.0,
    outdoor_rh_percent=60.0,
)
electrical = calculate_electrical_chain(it_load_kw=200.0)

print(f"CDU PUE: {cdu['pue']:.3f}")
print(f"Cooling plant COP: {plant['plant_cop']:.3f}")
print(f"Utility input: {electrical['total_facility_input_kw']:.2f} kW")
```

All power values are in kW, coolant flow in L/s, pressure drop in bar, temperatures in °C, and temperature difference in K unless a function documents otherwise. See each function's docstring for inputs, return fields, and validation behavior.

## Model assumptions and limitations / 模型假设与限制

- **Steady-state estimates:** These functions calculate operating-point estimates; they do not simulate time-domain thermal inertia, control sequences, component cycling, or transients.
- **Illustrative performance curves:** Chiller COP, UPS efficiency, tower fan power, and several default efficiencies/losses use simplified coefficients. Replace them with validated equipment data before using results for design decisions.
- **Simplified coolant properties:** Coolant properties are lookup values rather than temperature-dependent property models. The Novec 7100 entry does not make the model a validated two-phase boiling simulation.
- **Weather fallback:** A failed or unresolved weather request uses 25 °C and 60% RH, with a warning. Verify the displayed conditions before interpreting weather-dependent results.
- **Separate accounting boundaries:** CDU PUE is calculated by the CDU model from IT and CDU auxiliary power. The Executive Summary separately combines cooling-plant and electrical-loss terms. Understand the selected system boundary before comparing PUE values.
- **No redundancy or fault simulation:** Redundancy, failure modes, protection behavior, and equipment constraints are not comprehensively modeled.

该工具适合方案探索、参数敏感性分析和教学演示。任何设计、验收或运营决策都应使用经现场数据与设备厂商资料校准的模型，并由具备资质的工程人员复核。

## Repository hygiene / 仓库清理

Python bytecode and `__pycache__` directories are excluded by `.gitignore`. Recreate the virtual environment locally as needed; generated interpreter caches should not be committed.
