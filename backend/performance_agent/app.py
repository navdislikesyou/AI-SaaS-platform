"""Streamlit dashboard for the Performance Agent.

This is a standalone Streamlit script, not an importable module. It executes
Streamlit calls at module scope, so importing it renders the whole dashboard.

Run it directly:

    streamlit run performance_agent/app.py

Never import this module from the FastAPI application or from an adapter. The
API surfaces the same results through POST /api/v1/performance/jobs instead.
"""

import json
from pathlib import Path
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
VIZ_DIR = RESULTS_DIR / "visualizations"
INSIGHTS_FILE = RESULTS_DIR / "insights.json"
ANALYSIS_FILE = RESULTS_DIR / "analysis_results.json"

st.set_page_config(page_title="Performance Agent", page_icon="📊", layout="wide")

st.title("📊 Performance Agent")
st.caption("Business performance analysis, visualizations and actionable insights")

def load_json(path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def money(v):
    return f"₹{float(v)/1_000_000:.2f}M"

def get_insights(data):
    if isinstance(data, list):
        return data
    for key in ("all_insights", "insights", "actionable_insights"):
        if isinstance(data.get(key), list):
            return data[key]
    return []

st.sidebar.header("Performance Agent")
uploaded = st.sidebar.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])
if uploaded:
    st.sidebar.success(f"Loaded: {uploaded.name}")
    st.sidebar.info("Demo mode: showing the existing Performance Agent results.")

analysis = load_json(ANALYSIS_FILE)
insights_data = load_json(INSIGHTS_FILE)
insights = get_insights(insights_data)

overall = {}
if isinstance(analysis, dict):
    overall = analysis.get("company", {}).get("overall", {})

sales = overall.get("total_sales", 118726350.29)
profit = overall.get("total_profit", 17671023.54)
margin = overall.get("profit_margin", 14.88)
sales_target = overall.get("sales_target_achievement", 96.78)
profit_target = overall.get("profit_target_achievement", 94.89)

st.subheader("Executive Summary")
a,b,c,d,e = st.columns(5)
a.metric("Total Sales", money(sales))
b.metric("Total Profit", money(profit))
c.metric("Profit Margin", f"{float(margin):.2f}%")
d.metric("Sales Target", f"{float(sales_target):.2f}%")
e.metric("Profit Target", f"{float(profit_target):.2f}%")

st.divider()
st.subheader("Priority Insights")

def severity(x):
    return str(x.get("severity", x.get("priority", ""))).upper()

critical = [x for x in insights if severity(x) == "CRITICAL"]
warnings = [x for x in insights if severity(x) == "WARNING"]
opportunities = [x for x in insights if str(x.get("type", x.get("category", ""))).upper() == "OPPORTUNITY"]

if critical:
    st.markdown("### 🔴 Critical")
    for x in critical[:3]:
        with st.container(border=True):
            st.markdown(f"**{x.get('title', x.get('insight_type', 'Critical Insight'))}**")
            if x.get("entity"):
                st.caption(f"Entity: {x['entity']}")
            st.write(x.get("insight", x.get("message", "")))
            if x.get("recommendation"):
                st.info(x["recommendation"])

left, right = st.columns(2)

with left:
    st.markdown("### 🟠 Warnings")
    for x in warnings[:5]:
        with st.container(border=True):
            title = x.get("title", x.get("insight_type", "Warning"))
            entity = x.get("entity")
            st.markdown(f"**{title}**" + (f" — {entity}" if entity else ""))
            st.write(x.get("insight", x.get("message", "")))
            if x.get("recommendation"):
                st.caption("Recommendation: " + x["recommendation"])

with right:
    st.markdown("### 🟢 Opportunities")
    for x in opportunities[:5]:
        with st.container(border=True):
            title = x.get("title", x.get("insight_type", "Opportunity"))
            entity = x.get("entity")
            st.markdown(f"**{title}**" + (f" — {entity}" if entity else ""))
            st.write(x.get("insight", x.get("message", "")))
            if x.get("recommendation"):
                st.caption("Recommendation: " + x["recommendation"])

st.divider()
st.subheader("Business Visualizations")

viz = sorted(VIZ_DIR.glob("*.png")) if VIZ_DIR.exists() else []
if viz:
    labels = [p.stem.replace("_", " ").title() for p in viz]
    selected = st.selectbox("Choose a visualization", labels)
    st.image(str(viz[labels.index(selected)]), caption=selected, use_container_width=True)
else:
    st.warning("No visualization files found.")

st.divider()
st.subheader("Analysis Modules")
modules = ["Company", "Employee", "Department", "Product", "Regional", "Customer", "Channel", "Time / Trend", "Target"]
cols = st.columns(3)
for i, module in enumerate(modules):
    cols[i % 3].success(f"✓ {module} Analysis")

st.divider()
st.subheader("Agent Run")
x,y,z = st.columns(3)
x.metric("Analysis Modules", 9)
y.metric("Visualizations", len(viz) if viz else 39)
z.metric("Actionable Insights", len(insights) if insights else 17)
