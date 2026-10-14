"""
CDU Simulation Dashboard
冷却液分配单元仿真仪表板

An interactive Streamlit dashboard for simulating CDU performance in liquid cooling data centers.
Provides real-time adjustment of parameters and visualization of PUE, flow rates, and power consumption.

一个用于模拟液冷数据中心CDU性能的交互式Streamlit仪表板。
提供参数的实时调整以及PUE、流量和功耗的可视化。
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import numpy as np

# Add the current directory to the path to import thermal_engine and chiller_engine
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from thermal_engine import (
    calculate_cdu_performance,
    calculate_heat_load,
    get_coolant_properties,
    COOLANT_PROPERTIES,
    format_performance_report
)

from chiller_engine import (
    calculate_chiller_plant_total_power,
    calculate_chiller_power
)

from electrical_engine import (
    calculate_electrical_chain,
    calculate_ups_efficiency
)

import weather_client  # <-- Added import for weather client

# Page configuration
st.set_page_config(
    page_title="CDU Liquid Cooling Simulator",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for cyberpunk theme
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #00ffff;
        text-align: center;
        margin-bottom: 2rem;
        text-shadow: 0 0 10px #00ffff;
    }
    .metric-card {
        background-color: #0a0a0a;
        border: 1px solid #00ffff;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .stSlider > div > div > div > div {
        background-color: #00ffff;
    }
    .css-1aumxhk {
        background-color: #0a0a0a;
        background-image: none;
    }
</style>
""", unsafe_allow_html=True)

def main():
    if "outdoor_temp" not in st.session_state:
        st.session_state.outdoor_temp = 25.0
    if "outdoor_humidity" not in st.session_state:
        st.session_state.outdoor_humidity = 60.0

    # ── 供配电系统参数全局默认值 ──────────────────────────────────────────────
    # Tab 0 (Executive Summary) 在最顶部渲染时就需要这些值参与汇总计算，
    # 因此必须在所有 Tab 渲染之前完成初始化，防止 UnboundLocalError。
    # Tab 3 中的滑块会读取并覆盖这些 session_state，保持联动一致。
    if "ups_rated_kw" not in st.session_state:
        st.session_state.ups_rated_kw = 500.0           # UPS 额定容量 (kW)
    if "ups_nominal_efficiency" not in st.session_state:
        st.session_state.ups_nominal_efficiency = 0.94  # UPS 额定效率
    if "transformer_loss_factor" not in st.session_state:
        st.session_state.transformer_loss_factor = 0.02 # 变压器损耗因子
    if "pdu_loss_factor" not in st.session_state:
        st.session_state.pdu_loss_factor = 0.01         # PDU 损耗因子

    # 将 session_state 值映射到局部变量，供 Tab 0 直接使用
    ups_rated_kw           = st.session_state.ups_rated_kw
    ups_nominal_efficiency = st.session_state.ups_nominal_efficiency
    transformer_loss_factor = st.session_state.transformer_loss_factor
    pdu_loss_factor        = st.session_state.pdu_loss_factor
    # Header
    st.markdown('<h1 class="main-header">🌡️ CDU Liquid Cooling Simulator</h1>', unsafe_allow_html=True)
    st.markdown('<h3 class="main-header">冷却液分配单元液冷仿真系统</h3>', unsafe_allow_html=True)

    # Create tabs
    tab0, tab1, tab2, tab3 = st.tabs(["Executive Summary / 全站综合能效与 PUE 指挥大屏", "CDU Side / 冷却液分配单元", "Chiller Plant Side / 冷源系统仿真", "Electrical & UPS / 供配电系统仿真"])

    # Sidebar for inputs (shared across tabs)
    with st.sidebar:
        st.header("⚙️ Simulation Parameters / 仿真参数")
        st.markdown("Adjust the parameters below to simulate different operating conditions:")

        # IT Load
        it_power = st.slider(
            "IT Equipment Power (kW) / IT 设备功率 (kW)",
            min_value=10.0,
            max_value=500.0,
            value=100.0,
            step=10.0,
            help="Total power consumption of IT equipment"
        )

        # Temperature Difference
        delta_t = st.slider(
            "Temperature Difference ΔT (K) / 供回水温差 ΔT (K)",
            min_value=2.0,
            max_value=15.0,
            value=5.0,
            step=0.5,
            help="Difference between supply and return coolant temperature"
        )

        # Coolant Type
        coolant_options = list(COOLANT_PROPERTIES.keys())
        coolant_type = st.selectbox(
            "Coolant Type / 冷却液类型",
            options=coolant_options,
            index=0,  # Default to water
            help="Select the coolant fluid properties"
        )

        # Flow Rate (optional - can let system calculate)
        st.subheader("Flow Rate Setting / 流量设置")
        flow_mode = st.radio(
            "Flow Rate Mode / 流量模式",
            options=["Auto-calculate Required Flow", "Manual Flow Rate"],
            index=0
        )

        if flow_mode == "Auto-calculate Required Flow":
            flow_rate_l_s = None
            st.info("Flow rate will be calculated based on heat load and ΔT")
        else:
            flow_rate_l_s = st.slider(
                "Coolant Flow Rate (L/s) / 冷却液流量 (L/s)",
                min_value=0.5,
                max_value=50.0,
                value=5.0,
                step=0.5,
                help="Manually set coolant flow rate"
            )

        # Pump and System Parameters
        st.subheader("Pump & System Parameters / 泵浦及系统参数")

        col1, col2 = st.columns(2)
        with col1:
            primary_delta_p = st.slider(
                "Primary ΔP (bar) / 一次侧压降 (bar)",
                min_value=0.5,
                max_value=5.0,
                value=1.5,
                step=0.1
            )
        with col2:
            secondary_delta_p = st.slider(
                "Secondary ΔP (bar) / 二次侧压降 (bar)",
                min_value=0.5,
                max_value=5.0,
                value=2.0,
                step=0.1
            )

        pump_eff = st.slider(
            "Pump Efficiency / 泵浦效率",
            min_value=0.5,
            max_value=0.9,
            value=0.7,
            step=0.05
        )

        # Auxiliary Power
        st.subheader("Auxiliary Power / 辅助功率")
        fan_power = st.slider(
            "Fan Power (kW) / 风机功率 (kW)",
            min_value=0.0,
            max_value=10.0,
            value=2.0,
            step=0.5,
            help="Power for air-cooled condensers or radiators"
        )

        other_aux = st.slider(
            "Other Auxiliary (kW) / 其他辅助功率 (kW)",
            min_value=0.0,
            max_value=5.0,
            value=0.5,
            step=0.1,
            help="Controls, lighting, etc."
        )

    # Tab 0: Executive Summary / 全站综合能效与 PUE 指挥大屏
    with tab0:
        st.header("📊 Executive Summary / 全站综合能效与 PUE 指挥大屏")
        st.markdown("Aggregate view of total facility power consumption and comprehensive PUE metrics.")

        # Calculate all three modules' results using current sidebar inputs
        try:
            # 1. Calculate CDU performance (base IT load)
            cdu_results = calculate_cdu_performance(
                it_power_kw=it_power,
                delta_t_k=delta_t,
                coolant_type=coolant_type,
                flow_rate_l_s=flow_rate_l_s,
                primary_side_delta_p_bar=primary_delta_p,
                secondary_side_delta_p_bar=secondary_delta_p,
                pump_efficiency=pump_eff,
                fan_power_kw=fan_power,
                auxiliary_other_kw=other_aux
            )

            # 2. Calculate chiller plant performance (cooling power)
            chiller_results = calculate_chiller_plant_total_power(
                it_power_kw=it_power,
                outdoor_temp_c=st.session_state.outdoor_temp,
                outdoor_rh_percent=st.session_state.outdoor_humidity
            )

            # 3. Calculate electrical chain performance (electrical losses)
            electrical_results = calculate_electrical_chain(
                it_load_kw=it_power,
                ups_rated_kw=ups_rated_kw,
                ups_nominal_efficiency=ups_nominal_efficiency,
                transformer_loss_factor=transformer_loss_factor,
                pdu_loss_factor=pdu_loss_factor
            )

            # Extract key values
            P_it = it_power  # IT load from sidebar
            P_cooling = chiller_results['total_chiller_plant_power_kw']  # Total cooling plant power
            P_electrical_losses = electrical_results['ups_loss_kw'] + electrical_results['transformer_loss_kw'] + electrical_results['pdu_loss_kw']  # Total electrical losses

            # Calculate totals
            total_facility_power = P_it + P_cooling + P_electrical_losses
            comprehensive_pue = total_facility_power / P_it if P_it > 0 else 0

            # Calculate ratios for KPI display
            cooling_energy_ratio = (P_cooling / total_facility_power) * 100 if total_facility_power > 0 else 0
            electrical_loss_ratio = (P_electrical_losses / total_facility_power) * 100 if total_facility_power > 0 else 0

            # Display KPI cards
            st.subheader("🔑 Key Performance Indicators / 关键绩效指标")

            kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)

            with kpi_col1:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    label="📊 Comprehensive PUE / 综合 PUE",
                    value=f"{comprehensive_pue:.3f}",
                    delta=f"{comprehensive_pue - 1.0:.3f} from ideal"
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with kpi_col2:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    label="🔌 Total Facility Input / 总设施输入功率",
                    value=f"{total_facility_power:.2f} kW"
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with kpi_col3:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    label="💻 IT Total Power / IT 总功率",
                    value=f"{P_it:.2f} kW"
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with kpi_col4:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    label="❄️ Cooling Energy Ratio / 冷却能源比例",
                    value=f"{cooling_energy_ratio:.1f}%"
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with kpi_col5:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    label="⚡ Electrical Loss Ratio / 电气损耗比例",
                    value=f"{electrical_loss_ratio:.1f}%"
                )
                st.markdown('</div>', unsafe_allow_html=True)

            # Create charts
            st.subheader("📈 Power Consumption Analysis / 功耗分析")

            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                # Breakdown chart: IT, cooling, electrical losses
                breakdown_data = pd.DataFrame({
                    'Component': ['IT Equipment', 'Cooling Plant', 'Electrical Losses'],
                    'Power (kW)': [P_it, P_cooling, P_electrical_losses]
                })

                fig_breakdown = px.pie(
                    breakdown_data,
                    values='Power (kW)',
                    names='Component',
                    title='Total Facility Power Breakdown / 总设施功率分布',
                    color_discrete_sequence=['#00ffff', '#ff00ff', '#ffff00']
                )
                fig_breakdown.update_traces(textposition='inside', textinfo='percent+label')
                fig_breakdown.update_layout(
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )
                st.plotly_chart(fig_breakdown, width='stretch')

            with chart_col2:
                # Trend chart: PUE vs IT load and vs outdoor temperature
                st.markdown("### 📉 PUE Trends / PUE 趋势")

                # Generate data for PUE vs IT load (holding outdoor conditions constant)
                it_range = np.linspace(20, 500, 20)
                pue_vs_it = []
                for it_val in it_range:
                    # Recalculate all modules for each IT load value
                    try:
                        cdu_temp = calculate_cdu_performance(
                            it_power_kw=it_val,
                            delta_t_k=delta_t,
                            coolant_type=coolant_type,
                            flow_rate_l_s=flow_rate_l_s,
                            primary_side_delta_p_bar=primary_delta_p,
                            secondary_side_delta_p_bar=secondary_delta_p,
                            pump_efficiency=pump_eff,
                            fan_power_kw=fan_power,
                            auxiliary_other_kw=other_aux
                        )

                        chiller_temp = calculate_chiller_plant_total_power(
                            it_power_kw=it_val,
                            outdoor_temp_c=st.session_state.outdoor_temp,
                            outdoor_rh_percent=st.session_state.outdoor_humidity
                        )

                        electrical_temp = calculate_electrical_chain(
                            it_load_kw=it_val,
                            ups_rated_kw=ups_rated_kw,
                            ups_nominal_efficiency=ups_nominal_efficiency,
                            transformer_loss_factor=transformer_loss_factor,
                            pdu_loss_factor=pdu_loss_factor
                        )

                        P_it_temp = it_val
                        P_cooling_temp = chiller_temp['total_chiller_plant_power_kw']
                        P_electrical_losses_temp = electrical_temp['ups_loss_kw'] + electrical_temp['transformer_loss_kw'] + electrical_temp['pdu_loss_kw']
                        total_facility_temp = P_it_temp + P_cooling_temp + P_electrical_losses_temp
                        pue_temp = total_facility_temp / P_it_temp if P_it_temp > 0 else 0
                        pue_vs_it.append(pue_temp)
                    except:
                        pue_vs_it.append(0)

                # Generate data for PUE vs outdoor temperature (holding IT load constant)
                temp_range = np.linspace(-10, 50, 20)
                pue_vs_temp = []
                for temp_val in temp_range:
                    try:
                        # Recalculate chiller plant for each temperature value
                        chiller_temp = calculate_chiller_plant_total_power(
                            it_power_kw=it_power,
                            outdoor_temp_c=temp_val,
                            outdoor_rh_percent=st.session_state.outdoor_humidity
                        )

                        # Electrical and CDU remain constant for IT load
                        P_cooling_temp = chiller_temp['total_chiller_plant_power_kw']
                        P_electrical_losses_temp = electrical_results['ups_loss_kw'] + electrical_results['transformer_loss_kw'] + electrical_results['pdu_loss_kw']
                        P_it_temp = it_power
                        total_facility_temp = P_it_temp + P_cooling_temp + P_electrical_losses_temp
                        pue_temp = total_facility_temp / P_it_temp if P_it_temp > 0 else 0
                        pue_vs_temp.append(pue_temp)
                    except:
                        pue_vs_temp.append(0)

                fig_trends = go.Figure()
                fig_trends.add_trace(go.Scatter(
                    x=it_range,
                    y=pue_vs_it,
                    mode='lines+markers',
                    name='PUE vs IT Load',
                    line=dict(color='#00ffff', width=3)
                ))
                fig_trends.add_trace(go.Scatter(
                    x=temp_range,
                    y=pue_vs_temp,
                    mode='lines+markers',
                    name='PUE vs Outdoor Temp',
                    line=dict(color='#ff00ff', width=3)
                ))
                fig_trends.update_layout(
                    title='PUE Trends / PUE 趋势',
                    xaxis_title='IT Load (kW) / Outdoor Temperature (°C)',
                    yaxis_title='PUE',
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )
                st.plotly_chart(fig_trends, width='stretch')

        except Exception as e:
            st.error(f"❌ Error calculating executive summary: {str(e)}")
            st.exception(e)


    # Tab 1: CDU Side Simulation
    with tab1:
        # Calculate performance when button is clicked or parameters change
        if st.sidebar.button("🚀 Run Simulation / 运行仿真", type="primary", key="cdu_sim_button") or True:
            try:
                # Calculate CDU performance
                results = calculate_cdu_performance(
                    it_power_kw=it_power,
                    delta_t_k=delta_t,
                    coolant_type=coolant_type,
                    flow_rate_l_s=flow_rate_l_s,
                    primary_side_delta_p_bar=primary_delta_p,
                    secondary_side_delta_p_bar=secondary_delta_p,
                    pump_efficiency=pump_eff,
                    fan_power_kw=fan_power,
                    auxiliary_other_kw=other_aux
                )

                # Add IT power to results for display
                results['it_power_kw'] = it_power

                # Display results in columns
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🔥 Heat Load / 散热负荷",
                        value=f"{results['heat_load_kw']:.2f} kW"
                    )
                    st.metric(
                        label="💧 Required Flow / 所需流量",
                        value=f"{results['required_flow_l_s']:.3f} L/s"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with col2:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🔋 Total Auxiliary / 总辅助功率",
                        value=f"{results['total_auxiliary_kw']:.3f} kW"
                    )
                    st.metric(
                        label="⚡ Total Facility / 总设施功率",
                        value=f"{results['total_facility_power_kw']:.3f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with col3:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="📊 PUE",
                        value=f"{results['pue']:.3f}",
                        delta=f"{results['pue'] - 1.0:.3f} from ideal"
                    )
                    st.metric(
                        label="⚡ EER / 能效比",
                        value=f"{results['energy_efficiency_ratio']:.3f}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                # Create charts
                st.markdown("## 📈 Performance Charts / 性能图表")

                # Chart 1: Power breakdown
                power_data = pd.DataFrame({
                    'Component': ['IT Equipment', 'Pumps', 'Fans', 'Other Auxiliary'],
                    'Power (kW)': [
                        it_power,
                        results['total_pump_power_kw'],
                        fan_power,
                        other_aux
                    ]
                })

                fig_power = px.pie(
                    power_data,
                    values='Power (kW)',
                    names='Component',
                    title='Power Consumption Breakdown / 功耗分布',
                    color_discrete_sequence=['#00ffff', '#ff00ff', '#ffff00', '#ff0000']
                )
                fig_power.update_traces(textposition='inside', textinfo='percent+label')
                fig_power.update_layout(
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Chart 2: PUE vs IT Load (sensitivity)
                st.markdown("### 🔍 Sensitivity Analysis / 敏感性分析")

                # Generate data for PUE vs IT load
                it_range = np.linspace(20, 300, 20)
                pue_values = []
                for it_val in it_range:
                    res = calculate_cdu_performance(
                        it_power_kw=it_val,
                        delta_t_k=delta_t,
                        coolant_type=coolant_type,
                        flow_rate_l_s=flow_rate_l_s,
                        primary_side_delta_p_bar=primary_delta_p,
                        secondary_side_delta_p_bar=secondary_delta_p,
                        pump_efficiency=pump_eff,
                        fan_power_kw=fan_power,
                        auxiliary_other_kw=other_aux
                    )
                    pue_values.append(res['pue'])

                fig_pue = go.Figure()
                fig_pue.add_trace(go.Scatter(
                    x=it_range,
                    y=pue_values,
                    mode='lines+markers',
                    name='PUE',
                    line=dict(color='#00ffff', width=3)
                ))
                fig_pue.update_layout(
                    title='PUE vs IT Load Sensitivity / PUE 对 IT 负载的敏感性',
                    xaxis_title='IT Power (kW)',
                    yaxis_title='PUE',
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Chart 3: Flow rate vs ΔT
                st.markdown("### 💧 Flow Rate Analysis / 流量分析")

                # Generate data for flow rate vs delta T
                dt_range = np.linspace(2, 15, 20)
                flow_values = []
                for dt_val in dt_range:
                    _, required_flow, _ = calculate_heat_load(
                        it_power_kw=it_power,
                        delta_t_k=dt_val,
                        coolant_type=coolant_type
                    )
                    flow_values.append(required_flow)

                fig_flow = go.Figure()
                fig_flow.add_trace(go.Scatter(
                    x=dt_range,
                    y=flow_values,
                    mode='lines+markers',
                    name='Required Flow',
                    line=dict(color='#00ffff', width=3)
                ))
                fig_flow.update_layout(
                    title='Required Coolant Flow Rate vs ΔT / 所需冷却液流量 对比温差',
                    xaxis_title='Temperature Difference ΔT (K)',
                    yaxis_title='Flow Rate (L/s)',
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Display charts
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    st.plotly_chart(fig_power, width='stretch')
                    st.plotly_chart(fig_pue, width='stretch')
                with chart_col2:
                    st.plotly_chart(fig_flow, width='stretch')

                # Display detailed report
                with st.expander("📋 Detailed Engineering Report / 详细工程报告"):
                    st.text(format_performance_report(results))

                # Display coolant properties
                with st.expander("🧪 Coolant Properties / 冷却液物性"):
                    props = get_coolant_properties(coolant_type)
                    props_df = pd.DataFrame([
                        ["Specific Heat (kJ/(kg·K))", props["specific_heat"]],
                        ["Density (kg/m³)", props["density"]],
                        ["Viscosity (Pa·s)", props.get("viscosity", "N/A")],
                        ["Thermal Conductivity (W/(m·K))", props.get("thermal_conductivity", "N/A")]
                    ], columns=["Property", "Value"])
                    st.dataframe(props_df, hide_index=True, width='stretch')

            except Exception as e:
                st.error(f"❌ Error in simulation: {str(e)}")
                st.exception(e)

    # Tab 2: Chiller Plant Side Simulation
    with tab2:
        st.header("Chiller Plant Side Simulation / 冷源系统仿真")
        st.markdown("Simulate chiller plant performance based on IT load and outdoor conditions.")


        # Weather sync section
        st.subheader("🌍 真实气象联动 (Global Weather Live Sync)")
        city_name = st.text_input(
            "输入全球任意城市/地区名称或经纬度 (例如: Tokyo, London, 上海 或 39.9, 116.4)",
            placeholder="例如: Tokyo, London, 上海 或 39.9, 116.4",
            help="输入城市名称或经纬度以获取实时天气数据"
        )
        if st.button("获取实时天气 / Fetch Live Weather", key="weather_fetch_button"):
            if city_name.strip() == "":
                st.warning("请输入城市名称")
            else:
                temp, hum = weather_client.get_weather_by_city_name(city_name)
                st.session_state.outdoor_temp = temp
                st.session_state.outdoor_humidity = hum
                st.success(f"已更新 {city_name} 的实时天气: {temp}°C, {hum}%")

        # Additional outdoor temperature slider for chiller plant tab
        st.subheader("Outdoor Conditions / 室外条件")
        outdoor_temp = st.slider(
            "Outdoor Temperature (°C) / 室外温度 (°C)",
            min_value=-10.0,
            max_value=50.0,
            value=st.session_state.outdoor_temp,
            step=1.0,
            help="Outdoor dry bulb temperature"
        )

        outdoor_humidity = st.slider(
            "Outdoor Relative Humidity (%) / 室外相对湿度 (%)",
            min_value=0.0,
            max_value=100.0,
            value=st.session_state.outdoor_humidity,
            step=5.0,
            help="Outdoor relative humidity"
        )

        # Calculate chiller plant performance when button is clicked
        if st.sidebar.button("🚀 Run Simulation / 运行仿真", type="primary", key="chiller_sim_button") or True:
            try:
                # Calculate chiller plant performance
                chiller_results = calculate_chiller_plant_total_power(
                    it_power_kw=it_power,
                    outdoor_temp_c=outdoor_temp,
                    outdoor_rh_percent=outdoor_humidity
                )

                # Display chiller plant KPIs
                st.markdown("### 🔋 Chiller Plant Power Consumption / 冷源系统功耗")

                kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

                with kpi_col1:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="⚡ Chiller Power / 冷水机功率",
                        value=f"{chiller_results['chiller_power_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with kpi_col2:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🌡️ Cooling Tower Power / 冷却塔功率",
                        value=f"{chiller_results['tower_fan_power_kw'] + chiller_results['tower_pump_power_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with kpi_col3:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="💧 Primary Pump Power / 一次泵功率",
                        value=f"{chiller_results['primary_pump_power_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with kpi_col4:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🏭 Total Plant Power / 总系统功率",
                        value=f"{chiller_results['total_chiller_plant_power_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                # Display COP and efficiency metrics
                st.markdown("### 📊 Efficiency Metrics / 能效指标")

                eff_col1, eff_col2, eff_col3 = st.columns(3)

                with eff_col1:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="❄️ Chiller COP / 冷水机COP",
                        value=f"{chiller_results['chiller_cop']:.3f}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with eff_col2:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🏭 Plant COP / 系统COP",
                        value=f"{chiller_results['plant_cop']:.3f}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with eff_col3:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="📈 Part Load Ratio / 负荷比 (PLR)",
                        value=f"{chiller_results['plr']:.3f}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                # Create charts for chiller plant
                st.markdown("## 📈 Chiller Plant Performance Charts / 冷源系统性能图表")

                # Chart 1: Power breakdown
                st.markdown("### ⚡ Power Consumption Breakdown / 功耗分布")

                power_breakdown_data = pd.DataFrame({
                    'Component': ['Chiller', 'Cooling Tower Fan', 'Cooling Tower Pump', 'Primary Pump'],
                    'Power (kW)': [
                        chiller_results['chiller_power_kw'],
                        chiller_results['tower_fan_power_kw'],
                        chiller_results['tower_pump_power_kw'],
                        chiller_results['primary_pump_power_kw']
                    ]
                })

                fig_chiller_power = px.pie(
                    power_breakdown_data,
                    values='Power (kW)',
                    names='Component',
                    title='Chiller Plant Power Consumption Breakdown / 冷源系统功耗分布',
                    color_discrete_sequence=['#00ffff', '#ff00ff', '#ffff00', '#ff0000']
                )
                fig_chiller_power.update_traces(textposition='inside', textinfo='percent+label')
                fig_chiller_power.update_layout(
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Chart 2: COP vs PLR (Part Load Ratio)
                st.markdown("### 📉 COP vs Part Load Ratio / COP 随负荷比变化")

                # Generate data for COP vs PLR at current outdoor conditions
                plr_range = np.linspace(0.1, 1.0, 20)
                cop_values = []
                for plr_val in plr_range:
                    # Calculate chiller COP at this PLR
                    chiller_power_result = calculate_chiller_power(
                        cooling_load_kw=plr_val * 500.0,  # Assuming 500kW rated capacity
                        outdoor_temp_c=outdoor_temp,
                        outdoor_rh_percent=outdoor_humidity,
                        chiller_rated_capacity_kw=500.0
                    )
                    cop_values.append(chiller_power_result['cop'])

                fig_cop_plr = go.Figure()
                fig_cop_plr.add_trace(go.Scatter(
                    x=plr_range,
                    y=cop_values,
                    mode='lines+markers',
                    name='Chiller COP',
                    line=dict(color='#00ffff', width=3)
                ))
                fig_cop_plr.update_layout(
                    title='Chiller COP vs Part Load Ratio / 冷水机COP 随负荷比变化',
                    xaxis_title='Part Load Ratio (PLR)',
                    yaxis_title='COP',
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Chart 3: Plant COP vs Outdoor Temperature
                st.markdown("### 🌡️ Plant COP vs Outdoor Temperature / 系统COP 随室外温度变化")

                # Generate data for plant COP vs outdoor temp at current IT load
                temp_range = np.linspace(-10, 50, 20)
                plant_cop_values = []
                for temp_val in temp_range:
                    chiller_plant_result = calculate_chiller_plant_total_power(
                        it_power_kw=it_power,
                        outdoor_temp_c=temp_val,
                        outdoor_rh_percent=outdoor_humidity
                    )
                    plant_cop_values.append(chiller_plant_result['plant_cop'])

                fig_plant_cop_temp = go.Figure()
                fig_plant_cop_temp.add_trace(go.Scatter(
                    x=temp_range,
                    y=plant_cop_values,
                    mode='lines+markers',
                    name='Plant COP',
                    line=dict(color='#00ffff', width=3)
                ))
                fig_plant_cop_temp.update_layout(
                    title='Plant COP vs Outdoor Temperature / 系统COP 随室外温度变化',
                    xaxis_title='Outdoor Temperature (°C)',
                    yaxis_title='Plant COP',
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Display charts
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    st.plotly_chart(fig_chiller_power, width='stretch')
                    st.plotly_chart(fig_cop_plr, width='stretch')
                with chart_col2:
                    st.plotly_chart(fig_plant_cop_temp, width='stretch')

                # Display detailed chiller plant report
                with st.expander("📋 Detailed Chiller Plant Report / 详细冷源系统报告"):
                    report_text = f"""
CHILLER PLANT PERFORMANCE REPORT
冷源系统性能报告
{"="*60}
IT Load: {chiller_results['it_power_kw']:.2f} kW
Outdoor Temperature: {chiller_results['outdoor_temp_c']:.1f}°C
Outdoor RH: {chiller_results['outdoor_rh_percent']:.1f}%

CHILLER PERFORMANCE:
  Electrical Power: {chiller_results['chiller_power_kw']:.3f} kW
  COP: {chiller_results['chiller_cop']:.3f}
  Part Load Ratio (PLR): {chiller_results['plr']:.3f}
  Condenser Entering Temp: {chiller_results['condenser_entering_temp_c']:.2f}°C
  Heat Rejection: {chiller_results['chiller_heat_rejection_kw']:.3f} kW

COOLING TOWER PERFORMANCE:
  Fan Power: {chiller_results['tower_fan_power_kw']:.3f} kW
  Pump Power: {chiller_results['tower_pump_power_kw']:.3f} kW
  Condenser Water Flow: {chiller_results['condenser_water_flow_l_s']:.3f} L/s
  Condenser Entering Temp: {chiller_results['condenser_entering_temp_c_tower']:.2f}°C
  Condenser Leaving Temp: {chiller_results['condenser_leaving_temp_c']:.2f}°C

PRIMARY PUMP PERFORMANCE (Evaporator Loop):
  Pump Power: {chiller_results['primary_pump_power_kw']:.3f} kW
  Primary Flow: {chiller_results['primary_flow_l_s']:.3f} L/s

TOTAL CHILLER PLANT:
  Total Power: {chiller_results['total_chiller_plant_power_kw']:.3f} kW
  Plant COP (IT Power / Plant Power): {chiller_results['plant_cop']:.3f}
{"="*60}
                    """
                    st.text(report_text)

            except Exception as e:
                st.error(f"❌ Error in chiller plant simulation: {str(e)}")
                st.exception(e)

    # Tab 3: Electrical & UPS Side Simulation
    with tab3:
        st.header("Electrical & UPS Side Simulation / 供配电系统仿真")
        st.markdown("Simulate electrical distribution and UPS losses based on IT load and system configuration.")

        # Electrical system parameters
        st.subheader("Electrical System Parameters / 供配电系统参数")

        eff_col1, eff_col2 = st.columns(2)
        with eff_col1:
            ups_nominal_efficiency = st.slider(
                "UPS Nominal Efficiency (at Rated Load) / UPS 额定效率",
                min_value=0.80,
                max_value=0.99,
                value=st.session_state.ups_nominal_efficiency,
                step=0.01,
                key="ups_nominal_efficiency",
                help="UPS efficiency at 100% load (typical range 80%-99%)"
            )
        with eff_col2:
            ups_rated_kw = st.slider(
                "UPS Rated Capacity (kW) / UPS 额定容量 (kW)",
                min_value=100.0,
                max_value=2000.0,
                value=st.session_state.ups_rated_kw,
                step=50.0,
                key="ups_rated_kw",
                help="UPS rated power capacity"
            )

        loss_col1, loss_col2 = st.columns(2)
        with loss_col1:
            transformer_loss_factor = st.slider(
                "Transformer Loss Factor / 变压器损耗因子",
                min_value=0.00,
                max_value=0.10,
                value=st.session_state.transformer_loss_factor,
                step=0.001,
                key="transformer_loss_factor",
                help="Fraction of input power lost in transformer (typical 0.5%-5%)"
            )
        with loss_col2:
            pdu_loss_factor = st.slider(
                "PDU Loss Factor / PDU 损耗因子",
                min_value=0.00,
                max_value=0.10,
                value=st.session_state.pdu_loss_factor,
                step=0.001,
                key="pdu_loss_factor",
                help="Fraction of input power lost in PDU (typical 0.5%-5%)"
            )

        redundancy = st.selectbox(
            "Redundancy Configuration / 冗余架构配置",
            options=["N", "N+1", "2N"],
            index=0,
            help="Redundancy configuration (simplified - does not affect calculations in this model)"
        )

        # Calculate electrical chain performance when button is clicked
        if st.sidebar.button("🚀 Run Simulation / 运行仿真", type="primary", key="electrical_sim_button") or True:
            try:
                # Calculate electrical chain performance
                electrical_results = calculate_electrical_chain(
                    it_load_kw=it_power,
                    ups_rated_kw=ups_rated_kw,
                    ups_nominal_efficiency=ups_nominal_efficiency,
                    transformer_loss_factor=transformer_loss_factor,
                    pdu_loss_factor=pdu_loss_factor
                )

                # Display electrical system KPIs
                st.markdown("### 🔌 Electrical System Power Flow / 供配电系统功率流动")

                kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

                with kpi_col1:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🔋 UPS Loss Power / UPS 损耗功率",
                        value=f"{electrical_results['ups_loss_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with kpi_col2:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🔌 Transformer Loss / 变压器损耗",
                        value=f"{electrical_results['transformer_loss_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with kpi_col3:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🔌 PDU Loss / PDU 损耗",
                        value=f"{electrical_results['pdu_loss_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with kpi_col4:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🔌 Total Facility Input / 总设施输入功率",
                        value=f"{electrical_results['total_facility_input_kw']:.2f} kW"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                # Display efficiency metrics
                st.markdown("### 📊 Efficiency Metrics / 能效指标")

                eff_col1, eff_col2, eff_col3 = st.columns(3)

                with eff_col1:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="⚡ UPS Efficiency / UPS 效率",
                        value=f"{electrical_results['ups_efficiency']:.3f}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with eff_col2:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="🏭 Overall System Efficiency / 系统总体效率",
                        value=f"{electrical_results['overall_efficiency']:.3f}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                with eff_col3:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric(
                        label="📊 PUE (Total Input / IT Load) / PUE (总输入/IT负载)",
                        value=f"{1/electrical_results['overall_efficiency'] if electrical_results['overall_efficiency'] > 0 else float('inf'):.3f}"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

                # Create charts for electrical system
                st.markdown("## 📈 Electrical System Performance Charts / 供配电系统性能图表")

                # Chart 1: Loss distribution pie chart
                st.markdown("### 🥧 Loss Distribution Pie Chart / 损耗占比饼图")

                loss_data = pd.DataFrame({
                    'Component': ['UPS Loss', 'Transformer Loss', 'PDU Loss'],
                    'Power Loss (kW)': [
                        electrical_results['ups_loss_kw'],
                        electrical_results['transformer_loss_kw'],
                        electrical_results['pdu_loss_kw']
                    ]
                })

                fig_loss_pie = px.pie(
                    loss_data,
                    values='Power Loss (kW)',
                    names='Component',
                    title='Electrical System Loss Distribution / 供配电系统损耗占比',
                    color_discrete_sequence=['#ff0000', '#00ff00', '#0000ff']
                )
                fig_loss_pie.update_traces(textposition='inside', textinfo='percent+label')
                fig_loss_pie.update_layout(
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Chart 2: UPS efficiency vs PLR
                st.markdown("### 📉 UPS Efficiency vs Part Load Ratio / UPS 效率随负荷比变化")

                # Generate data for UPS efficiency vs PLR at current nominal efficiency
                plr_range = np.linspace(0.05, 1.0, 20)
                eff_values = []
                for plr_val in plr_range:
                    eff = calculate_ups_efficiency(plr_val, ups_nominal_efficiency)
                    eff_values.append(eff)

                fig_ups_eff = go.Figure()
                fig_ups_eff.add_trace(go.Scatter(
                    x=plr_range,
                    y=eff_values,
                    mode='lines+markers',
                    name='UPS Efficiency',
                    line=dict(color='#00ffff', width=3)
                ))
                fig_ups_eff.update_layout(
                    title='UPS Efficiency vs Part Load Ratio / UPS 效率随负荷比变化',
                    xaxis_title='Part Load Ratio (PLR)',
                    yaxis_title='Efficiency',
                    plot_bgcolor='#0a0a0a',
                    paper_bgcolor='#0a0a0a',
                    font_color='#00ffff'
                )

                # Display charts
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    st.plotly_chart(fig_loss_pie, width='stretch')
                    st.plotly_chart(fig_ups_eff, width='stretch')
                # chart_col2 left empty for now, or we could add another chart
                with chart_col2:
                    st.write("")  # placeholder

                # Display detailed electrical report
                with st.expander("📋 Detailed Electrical System Report / 详细供配电系统报告"):
                    report_text = f"""
ELECTRICAL SYSTEM PERFORMANCE REPORT
供配电系统性能报告
{"="*60}
IT Load: {electrical_results['it_load_kw']:.2f} kW
UPS Rated Capacity: {ups_rated_kw:.2f} kW
UPS Nominal Efficiency (at Rated Load): {ups_nominal_efficiency:.3f}
Transformer Loss Factor: {transformer_loss_factor:.3f}
PDU Loss Factor: {pdu_loss_factor:.3f}
Redundancy Configuration: {redundancy}

POWER FLOW:
  IT Load (Output): {electrical_results['it_load_kw']:.3f} kW
  PDU Input: {electrical_results['pdu_input_kw']:.3f} kW
  PDU Loss: {electrical_results['pdu_loss_kw']:.3f} kW
  UPS Input: {electrical_results['ups_input_kw']:.3f} kW
  UPS Loss: {electrical_results['ups_loss_kw']:.3f} kW
  UPS Output: {electrical_results['ups_output_kw']:.3f} kW
  Transformer Input: {electrical_results['transformer_input_kw']:.3f} kW
  Transformer Loss: {electrical_results['transformer_loss_kw']:.3f} kW
  Transformer Output: {electrical_results['transformer_output_kw']:.3f} kW

EFFICIENCY:
  UPS PLR: {electrical_results['ups_plr']:.3f}
  UPS Efficiency: {electrical_results['ups_efficiency']:.3f}
  Overall System Efficiency: {electrical_results['overall_efficiency']:.3f}
  Overall PUE (Total Input / IT Load): {1/electrical_results['overall_efficiency'] if electrical_results['overall_efficiency'] > 0 else float('inf'):.3f}
{"="*60}
                    """
                    st.text(report_text)

            except Exception as e:
                st.error(f"❌ Error in electrical system simulation: {str(e)}")
                st.exception(e)

if __name__ == "__main__":
    main()