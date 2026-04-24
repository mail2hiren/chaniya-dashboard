import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import date

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Chaniya Analytics",
    page_icon="👗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #f5f4f0; }
  [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e5e3da; }
  [data-testid="stSidebar"] h1 { font-size: 16px !important; }
  .block-container { padding-top: 1.2rem; padding-bottom: 1rem; }
  div[data-testid="metric-container"] {
    background: #ffffff; border: 0.5px solid #e5e3da;
    border-radius: 9px; padding: 12px 16px;
  }
  div[data-testid="metric-container"] label { font-size: 11px !important; color: #9a9891; }
  div[data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 22px !important; }
  .kpi-green  { border-left: 3px solid #2d7a3a !important; }
  .kpi-amber  { border-left: 3px solid #b8730f !important; }
  .kpi-red    { border-left: 3px solid #b83232 !important; }
  .kpi-blue   { border-left: 3px solid #185FA5 !important; }
  .info-box   { background:#fff7e0; border:0.5px solid #f5c87a; border-radius:8px;
                padding:10px 14px; font-size:12px; color:#6b4208; margin-bottom:12px; }
  .section-hdr { font-size:11px; font-weight:600; color:#9a9891; text-transform:uppercase;
                 letter-spacing:.7px; margin: 14px 0 6px; }
  h2 { font-size: 15px !important; }
  h3 { font-size: 13px !important; }
</style>
""", unsafe_allow_html=True)

TODAY = pd.Timestamp(date.today())

# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING & PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner="Loading data…")
def load_data(inv_bytes, sal_bytes):
    inv = pd.read_excel(inv_bytes)
    sal = pd.read_excel(sal_bytes)

    # ── Clean invoice ──────────────────────────────────────────────────────
    inv = inv[inv["Size"] != "Size"].copy()
    for c in ["Quantity", "Price", "MRP"]:
        inv[c] = pd.to_numeric(inv[c], errors="coerce")
    inv["Invoice Date"] = pd.to_datetime(inv["Invoice Date"])
    inv["Color"] = inv["Color"].astype(str)
    inv["Size"]  = pd.to_numeric(inv["Size"], errors="coerce")

    # ── Clean sales ────────────────────────────────────────────────────────
    for c in ["Quantity", "Total", "MRP"]:
        sal[c] = pd.to_numeric(sal[c], errors="coerce")
    sal["Sales Date"] = pd.to_datetime(sal["Sales Date"])

    sal_pos = sal[sal["Quantity"] > 0].copy()
    sal_ret = sal[sal["Quantity"] < 0].copy()

    # ── First invoice date per barcode → stock age ─────────────────────────
    first_inv = (
        inv.groupby("Bar Code")["Invoice Date"].min()
        .reset_index()
        .rename(columns={"Invoice Date": "First_Invoice_Date"})
    )
    first_inv["Stock_Age_Days"] = (TODAY - first_inv["First_Invoice_Date"]).dt.days

    def age_bucket(d):
        if d <= 90:  return "🟢 Fresh (≤90d)"
        if d <= 180: return "🟡 Aging (91-180d)"
        return "🔴 Old (>180d)"

    first_inv["Age_Bucket"] = first_inv["Stock_Age_Days"].apply(age_bucket)

    # ── Per-barcode invoice summary ────────────────────────────────────────
    bc_agg = (
        inv.groupby("Bar Code")
        .agg(
            Total_Invoiced=("Quantity", "sum"),
            Invoice_Value =("Price",    lambda x: float((x * inv.loc[x.index, "Quantity"]).sum())),
            MRP_Value     =("MRP",      lambda x: float((x * inv.loc[x.index, "Quantity"]).sum())),
            Color         =("Color",    "first"),
            Size          =("Size",     "first"),
        )
        .reset_index()
    )

    # ── Per-barcode sales summary ──────────────────────────────────────────
    sal_bc = (
        sal_pos.groupby("URD")
        .agg(Sold=("Quantity", "sum"), Sales_Val=("Total", "sum"))
        .reset_index()
        .rename(columns={"URD": "Bar Code"})
    )

    merged = (
        bc_agg
        .merge(first_inv[["Bar Code", "First_Invoice_Date", "Stock_Age_Days", "Age_Bucket"]], on="Bar Code", how="left")
        .merge(sal_bc, on="Bar Code", how="left")
    )
    merged["Sold"]      = merged["Sold"].fillna(0)
    merged["Sales_Val"] = merged["Sales_Val"].fillna(0)
    merged["Unsold"]    = merged["Total_Invoiced"] - merged["Sold"]
    merged["ST_Pct"]    = (merged["Sold"] / merged["Total_Invoiced"] * 100).clip(0, 100).round(1)
    merged["Unit_MRP"]  = (merged["MRP_Value"] / merged["Total_Invoiced"].replace(0, np.nan)).fillna(0)
    merged["Cash_Blocked_MRP"] = (merged["Unsold"] * merged["Unit_MRP"]).clip(lower=0)

    # ── Branch summary ─────────────────────────────────────────────────────
    br_inv = (
        inv.groupby("Branch")
        .agg(Inv_Qty=("Quantity","sum"),
             Inv_Val=("Price", lambda x: float((x * inv.loc[x.index,"Quantity"]).sum())))
        .reset_index()
    )
    br_sal = (
        sal_pos.groupby("Branch")
        .agg(Sal_Qty=("Quantity","sum"), Sal_Val=("Total","sum"))
        .reset_index()
    )
    branch = br_inv.merge(br_sal, on="Branch", how="outer").fillna(0)
    branch["ST"]     = (branch["Sal_Qty"] / branch["Inv_Qty"].replace(0, np.nan) * 100).round(1).fillna(0)
    branch["Unsold"] = branch["Inv_Qty"] - branch["Sal_Qty"]
    branch = branch[branch["Inv_Qty"] > 0].sort_values("Sal_Qty", ascending=False).reset_index(drop=True)

    # ── Monthly trend ──────────────────────────────────────────────────────
    import calendar
    def month_key(m):
        try:
            parts = m.split("-")
            mon = list(calendar.month_abbr).index(parts[0][:3])
            return int(parts[1]) * 100 + mon
        except:
            return 0

    mi = inv.groupby("Month")["Quantity"].sum().to_dict()
    ms = sal_pos.groupby("Month")["Quantity"].sum().to_dict()
    all_months = sorted(set(list(mi.keys()) + list(ms.keys())), key=month_key)
    monthly = pd.DataFrame({
        "Month":    all_months,
        "Invoiced": [int(mi.get(m, 0)) for m in all_months],
        "Sold":     [int(ms.get(m, 0)) for m in all_months],
    })

    # ── Color performance ──────────────────────────────────────────────────
    bc_color = inv[["Bar Code", "Color"]].drop_duplicates("Bar Code")
    sal_color = sal_pos.merge(bc_color, left_on="URD", right_on="Bar Code", how="left")
    color_sal = sal_color.groupby("Color")["Quantity"].sum().reset_index().rename(columns={"Quantity":"Sold"})
    color_inv = inv.groupby("Color")["Quantity"].sum().reset_index().rename(columns={"Quantity":"Invoiced"})
    color_df  = color_inv.merge(color_sal, on="Color", how="left").fillna(0)
    color_df["ST"] = (color_df["Sold"] / color_df["Invoiced"] * 100).clip(0, 150).round(1)
    color_df = color_df.sort_values("Invoiced", ascending=False).head(20).reset_index(drop=True)

    # ── Size performance ───────────────────────────────────────────────────
    bc_size = inv[["Bar Code", "Size"]].drop_duplicates("Bar Code")
    sal_size = sal_pos.merge(bc_size, left_on="URD", right_on="Bar Code", how="left")
    size_sal = sal_size.groupby("Size")["Quantity"].sum().reset_index().rename(columns={"Quantity":"Sold"})
    size_inv = inv.groupby("Size")["Quantity"].sum().reset_index().rename(columns={"Quantity":"Invoiced"})
    size_df  = size_inv.merge(size_sal, on="Size", how="left").fillna(0)
    size_df["ST"] = (size_df["Sold"] / size_df["Invoiced"] * 100).clip(0, 100).round(1)
    size_df = size_df[size_df["Size"].isin([38, 40, 42])].reset_index(drop=True)

    return dict(
        inv=inv, sal=sal, sal_pos=sal_pos, sal_ret=sal_ret,
        merged=merged, branch=branch, monthly=monthly,
        color_df=color_df, size_df=size_df,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CHART HELPERS
# ══════════════════════════════════════════════════════════════════════════════
COLORS = {"green":"#2d7a3a","amber":"#b8730f","red":"#b83232","blue":"#185FA5","gray":"#9a9891"}

def st_color(v):
    if v >= 80: return COLORS["green"]
    if v >= 65: return COLORS["amber"]
    return COLORS["red"]

def plotly_defaults(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor ="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=28, b=0),
        font=dict(family="system-ui, sans-serif", size=11, color="#1b1a17"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hoverlabel=dict(bgcolor="#fff", font_size=11),
    )
    fig.update_xaxes(showgrid=False, tickfont_size=10, title_font_size=11)
    fig.update_yaxes(gridcolor="#ebebeb", tickfont_size=10, title_font_size=11)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — FILE UPLOAD + FILTERS
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 👗 Chaniya Analytics")
    st.markdown("<div style='font-size:10px;color:#9a9891;text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px;'>Kerala Retail Network</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📂 Data Files")
    st.markdown("<div style='font-size:11px;color:#555;margin-bottom:6px;'>Drop your weekly Excel files here to refresh the dashboard.</div>", unsafe_allow_html=True)

    inv_file = st.file_uploader("Invoice Data (.xlsx)", type=["xlsx"], key="inv")
    sal_file = st.file_uploader("Sales Data (.xlsx)",   type=["xlsx"], key="sal")

    # Fall back to bundled sample files
    if inv_file is None:
        inv_src = "Invoice_Data.xlsx"
    else:
        inv_src = inv_file

    if sal_file is None:
        sal_src = "Sales_Data.xlsx"
    else:
        sal_src = sal_file

    st.markdown("---")

    data = load_data(inv_src, sal_src)
    merged = data["merged"]
    branch = data["branch"]

    st.markdown("### 🔍 Filters")

    # Branch filter
    branch_opts = ["All Branches"] + sorted(data["branch"]["Branch"].tolist())
    sel_branch = st.selectbox("Branch", branch_opts)

    # Stock age filter
    age_opts = ["All", "🟢 Fresh (≤90d)", "🟡 Aging (91-180d)", "🔴 Old (>180d)"]
    sel_age = st.selectbox("Stock Age", age_opts)

    # Size filter
    size_opts = ["All Sizes", "38", "40", "42"]
    sel_size = st.selectbox("Size", size_opts)

    st.markdown("---")
    st.markdown(f"<div style='font-size:10px;color:#9a9891;'>Data range: Jul 2024 – Apr 2026<br>18 branches · 668 SKUs<br>As of {TODAY.strftime('%d %b %Y')}</div>", unsafe_allow_html=True)

    # Page selector
    st.markdown("---")
    st.markdown("### 📄 Pages")
    page = st.radio(
        "Navigate",
        ["📊 Executive Summary", "⭐ Best Sellers", "🚨 Dead Stock",
         "🎨 Color & Size", "🏪 Branch Analytics", "⚡ Action Decisions"],
        label_visibility="collapsed",
    )


# ── Apply filters to merged ────────────────────────────────────────────────────
filt = merged.copy()
if sel_branch != "All Branches":
    bc_in_branch = data["inv"][data["inv"]["Branch"] == sel_branch]["Bar Code"].unique()
    filt = filt[filt["Bar Code"].isin(bc_in_branch)]
if sel_age != "All":
    filt = filt[filt["Age_Bucket"] == sel_age]
if sel_size != "All Sizes":
    filt = filt[filt["Size"] == int(sel_size)]


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: EXECUTIVE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Executive Summary":
    st.markdown("## 📊 Executive Summary — What is the overall business health?")

    st.markdown("""<div class='info-box'>
    ⚠️ <b>Context note:</b> 583 of 667 invoiced SKUs are &gt;180 days old — this reflects a long sales cycle 
    (Jul–Aug 2024 stock still selling). The 79% sell-through is healthy. 
    Fresh SKUs (47 barcodes, invoiced Dec 2025–Apr 2026) have low ST% because they are early in their cycle — this is <b>expected, not alarming</b>.
    </div>""", unsafe_allow_html=True)

    tot_inv   = int(filt["Total_Invoiced"].sum())
    tot_sold  = int(filt["Sold"].sum())
    tot_unsold= int(filt["Unsold"].sum())
    st_pct    = round(tot_sold / tot_inv * 100, 1) if tot_inv else 0
    inv_val   = round(filt["Invoice_Value"].sum() / 100000, 2)
    sal_val   = round(filt["Sales_Val"].sum() / 100000, 2)
    cash_blk  = round(filt["Cash_Blocked_MRP"].sum() / 100000, 2)
    old_skus  = int((filt["Age_Bucket"] == "🔴 Old (>180d)").sum())

    c1,c2,c3,c4,c5,c6,c7,c8 = st.columns(8)
    c1.metric("📦 Invoiced Qty",    f"{tot_inv:,}")
    c2.metric("💰 Invoice Value",   f"₹{inv_val}L")
    c3.metric("✅ Sold Qty",         f"{tot_sold:,}")
    c4.metric("💵 Sales Value",      f"₹{sal_val}L")
    c5.metric("📈 Sell-Through",     f"{st_pct}%")
    c6.metric("📦 Unsold Qty",       f"{tot_unsold:,}")
    c7.metric("🔒 Cash Blocked",     f"₹{cash_blk}L")
    c8.metric("⚠️ Old SKUs >180d",  f"{old_skus}")

    st.markdown("<div class='section-hdr'>Monthly Trend — Invoice vs Sales</div>", unsafe_allow_html=True)

    mdf = data["monthly"]
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Bar(name="Invoiced", x=mdf["Month"], y=mdf["Invoiced"],
                               marker_color="rgba(24,95,165,0.55)", marker_line_width=0))
    fig_trend.add_trace(go.Bar(name="Sold", x=mdf["Month"], y=mdf["Sold"],
                               marker_color="#2d7a3a", marker_line_width=0))
    fig_trend.update_layout(barmode="group", height=280, title="Monthly Invoice vs Sold Quantity")
    plotly_defaults(fig_trend)
    st.plotly_chart(fig_trend, use_container_width=True)

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("<div class='section-hdr'>Stock Age Breakdown (SKU count)</div>", unsafe_allow_html=True)
        age_counts = filt["Age_Bucket"].value_counts().reset_index()
        age_counts.columns = ["Bucket", "Count"]
        fig_age = px.pie(age_counts, names="Bucket", values="Count",
                         color="Bucket",
                         color_discrete_map={
                             "🟢 Fresh (≤90d)": "#2d7a3a",
                             "🟡 Aging (91-180d)": "#b8730f",
                             "🔴 Old (>180d)": "#b83232"},
                         hole=0.6)
        fig_age.update_traces(textposition="outside", textfont_size=11)
        fig_age.update_layout(height=280, showlegend=True, title="SKUs by Stock Age")
        plotly_defaults(fig_age)
        st.plotly_chart(fig_age, use_container_width=True)

    with col_r:
        st.markdown("<div class='section-hdr'>Top 10 Best Sellers — Fresh stock (≤90d)</div>", unsafe_allow_html=True)
        fresh = filt[filt["Age_Bucket"] == "🟢 Fresh (≤90d)"].copy()
        top10 = fresh[fresh["Total_Invoiced"] >= 3].sort_values("ST_Pct", ascending=False).head(10)
        if len(top10):
            top10["Label"] = top10["Bar Code"] + " C" + top10["Color"].astype(str) + " Sz" + top10["Size"].astype(str)
            fig_top = px.bar(top10, x="ST_Pct", y="Label", orientation="h",
                             color="ST_Pct", color_continuous_scale=["#b83232","#b8730f","#2d7a3a"],
                             range_color=[0,100], labels={"ST_Pct":"ST%","Label":""})
            fig_top.update_coloraxes(showscale=False)
            fig_top.update_layout(height=280, title="Top Fresh SKUs by ST%")
            plotly_defaults(fig_top)
            st.plotly_chart(fig_top, use_container_width=True)
        else:
            st.info("No fresh SKUs matching current filters.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: BEST SELLERS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⭐ Best Sellers":
    st.markdown("## ⭐ Best Sellers — Which SKUs to reorder now?")

    fresh_all = filt[filt["Age_Bucket"] == "🟢 Fresh (≤90d)"].copy()
    c1,c2,c3,c4 = st.columns(4)
    top_st = fresh_all["ST_Pct"].max() if len(fresh_all) else 0
    c1.metric("🏆 Top Fresh ST%",    f"{top_st}%")
    c2.metric("🆕 Fresh SKUs",        f"{len(fresh_all)}")
    c3.metric("📊 Best Color (Vol)",  "#359 — 75.6% ST")
    c4.metric("🎯 Best Color (ST%)",  "#409 — 84.2% ST")

    st.markdown("<div class='section-hdr'>Top Fresh SKUs ranked by Sell-Through % — Old stock excluded</div>", unsafe_allow_html=True)
    top_fresh = fresh_all[fresh_all["Total_Invoiced"] >= 3].sort_values("ST_Pct", ascending=False).head(15)
    if len(top_fresh):
        top_fresh = top_fresh.copy()
        top_fresh["SKU Label"] = top_fresh["Bar Code"] + " | Color #" + top_fresh["Color"].astype(str) + " | Size " + top_fresh["Size"].astype(str)
        top_fresh["Bar Color"] = top_fresh["ST_Pct"].apply(st_color)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=top_fresh["ST_Pct"], y=top_fresh["SKU Label"], orientation="h",
            marker_color=top_fresh["Bar Color"], text=top_fresh["ST_Pct"].astype(str)+"%",
            textposition="outside", marker_line_width=0,
        ))
        fig.update_layout(height=420, title="Fresh SKUs — Sell-Through %", xaxis_range=[0,115])
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No fresh SKUs with ≥3 units invoiced in current filter.")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("<div class='section-hdr'>Top 15 Color Codes — Volume & Sell-Through</div>", unsafe_allow_html=True)
        cdf = data["color_df"].copy()
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(name="Invoiced", x=cdf["Color"].astype(str), y=cdf["Invoiced"],
                               marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
        fig_c.add_trace(go.Bar(name="Sold", x=cdf["Color"].astype(str), y=cdf["Sold"],
                               marker_color="#2d7a3a", marker_line_width=0))
        fig_c.update_layout(barmode="group", height=300, title="Color Code — Invoiced vs Sold")
        plotly_defaults(fig_c)
        st.plotly_chart(fig_c, use_container_width=True)

    with col_r:
        st.markdown("<div class='section-hdr'>Size Performance — Supply vs Sold</div>", unsafe_allow_html=True)
        sdf = data["size_df"].copy()
        fig_s = go.Figure()
        fig_s.add_trace(go.Bar(name="Invoiced", x=sdf["Size"].astype(str), y=sdf["Invoiced"],
                               marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
        fig_s.add_trace(go.Bar(name="Sold", x=sdf["Size"].astype(str), y=sdf["Sold"],
                               marker_color="#2d7a3a", marker_line_width=0))
        for _, row in sdf.iterrows():
            fig_s.add_annotation(x=str(int(row["Size"])), y=row["Invoiced"]+200,
                                 text=f"{row['ST']}% ST", showarrow=False, font_size=11, font_color="#555")
        fig_s.update_layout(barmode="group", height=300, title="Size 38 / 40 / 42 — Invoiced vs Sold")
        plotly_defaults(fig_s)
        st.plotly_chart(fig_s, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DEAD STOCK
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🚨 Dead Stock":
    st.markdown("## 🚨 Dead Stock — Where is ₹30.9L of cash blocked?")

    old = filt[filt["Age_Bucket"] == "🔴 Old (>180d)"]
    aging = filt[filt["Age_Bucket"] == "🟡 Aging (91-180d)"]

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("🔴 Old SKUs (>180d)",  f"{len(old)}")
    c2.metric("💰 Cash Blocked @MRP", f"₹{round(filt['Cash_Blocked_MRP'].sum()/100000,2)}L")
    c3.metric("🟡 Aging SKUs",         f"{len(aging)}")
    c4.metric("0% ST SKUs",            f"{int((filt['ST_Pct']==0).sum())}")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("<div class='section-hdr'>Unsold stock by branch</div>", unsafe_allow_html=True)
        br = data["branch"].copy()
        br = br[br["Unsold"] > 0].sort_values("Unsold", ascending=False)
        bar_colors = br["Unsold"].apply(lambda v: "#b83232" if v > 600 else "#b8730f" if v > 300 else "#888")
        fig_br = go.Figure(go.Bar(x=br["Branch"], y=br["Unsold"],
                                  marker_color=bar_colors.tolist(), marker_line_width=0,
                                  text=br["Unsold"].astype(int), textposition="outside"))
        fig_br.update_layout(height=300, title="Unsold Units by Branch")
        plotly_defaults(fig_br)
        st.plotly_chart(fig_br, use_container_width=True)

    with col_r:
        st.markdown("<div class='section-hdr'>Branch efficiency — ST% vs Unsold qty</div>", unsafe_allow_html=True)
        br2 = data["branch"].copy()
        br2 = br2[br2["Inv_Qty"] > 0]
        br2["color"] = br2["ST"].apply(lambda v: "#2d7a3a" if v >= 85 else "#b8730f" if v >= 70 else "#b83232")
        fig_sc = px.scatter(br2, x="ST", y="Unsold", text="Branch",
                            size="Inv_Qty", color="ST",
                            color_continuous_scale=["#b83232","#b8730f","#2d7a3a"],
                            range_color=[50,100],
                            labels={"ST":"Sell-Through %","Unsold":"Unsold Units"})
        fig_sc.update_traces(textposition="top center", textfont_size=9, marker_line_width=0)
        fig_sc.update_coloraxes(showscale=False)
        fig_sc.update_layout(height=300, title="ST% vs Unsold (bubble = supply size)")
        plotly_defaults(fig_sc)
        st.plotly_chart(fig_sc, use_container_width=True)

    st.markdown("<div class='section-hdr'>Dead stock register — lowest ST%, oldest first</div>", unsafe_allow_html=True)
    dead = (
        filt[filt["ST_Pct"] < 30]
        .sort_values(["Stock_Age_Days","ST_Pct"], ascending=[False,True])
        .head(30)
        [["Bar Code","Color","Size","Stock_Age_Days","Age_Bucket","Total_Invoiced","Sold","ST_Pct","Cash_Blocked_MRP"]]
        .rename(columns={
            "Bar Code":"SKU","Stock_Age_Days":"Age (Days)","Age_Bucket":"Stage",
            "Total_Invoiced":"Invoiced","ST_Pct":"ST%","Cash_Blocked_MRP":"Cash Blocked (₹)"
        })
    )
    dead["Cash Blocked (₹)"] = dead["Cash Blocked (₹)"].round(0).astype(int)

    def color_st(val):
        color = "#b83232" if val < 10 else "#b8730f" if val < 20 else "#888"
        return f"color: {color}; font-weight: 600"

    def color_age(val):
        color = "#b83232" if val > 365 else "#b8730f" if val > 180 else "#888"
        return f"color: {color}"

    st.dataframe(
        dead.style
        .applymap(color_st, subset=["ST%"])
        .applymap(color_age, subset=["Age (Days)"]),
        use_container_width=True, height=400
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: COLOR & SIZE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🎨 Color & Size":
    st.markdown("## 🎨 Color & Size Trends — What styles drive demand?")

    cdf = data["color_df"]
    best_c  = cdf.loc[cdf["ST"].idxmax(), "Color"]
    worst_c = cdf.loc[cdf[cdf["ST"] < 110]["ST"].idxmin(), "Color"]
    sdf = data["size_df"]

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("🏆 Best Color (ST%)",  f"#{best_c}",  f"{cdf.loc[cdf['Color']==best_c,'ST'].values[0]}% ST")
    c2.metric("🏆 Best Size",          "Size 38",     "70.6% ST")
    c3.metric("⚠️ Worst Color",       f"#{worst_c}", f"{cdf.loc[cdf['Color']==worst_c,'ST'].values[0]}% ST")
    c4.metric("⚠️ Weakest Size",      "Size 42",     "54.2% ST")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("<div class='section-hdr'>Color code sell-through % — top 15 by volume</div>", unsafe_allow_html=True)
        cdf_s = cdf.copy()
        cdf_s["bar_color"] = cdf_s["ST"].apply(lambda v: st_color(min(v, 100)))
        cdf_s = cdf_s.sort_values("ST", ascending=True)
        fig_cst = go.Figure(go.Bar(
            x=cdf_s["ST"].clip(0,100), y=cdf_s["Color"].astype(str),
            orientation="h", marker_color=cdf_s["bar_color"].tolist(),
            text=cdf_s["ST"].clip(0,100).astype(str)+"%", textposition="outside",
            marker_line_width=0,
        ))
        fig_cst.update_layout(height=420, title="Color Code — Sell-Through %", xaxis_range=[0,115])
        plotly_defaults(fig_cst)
        st.plotly_chart(fig_cst, use_container_width=True)

    with col_r:
        st.markdown("<div class='section-hdr'>Size performance — supply vs sold</div>", unsafe_allow_html=True)
        fig_sz = go.Figure()
        fig_sz.add_trace(go.Bar(name="Invoiced", x=sdf["Size"].astype(str), y=sdf["Invoiced"],
                                marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
        fig_sz.add_trace(go.Bar(name="Sold", x=sdf["Size"].astype(str), y=sdf["Sold"],
                                marker_color="#2d7a3a", marker_line_width=0))
        fig_sz.update_layout(barmode="group", height=280, title="Size — Invoiced vs Sold")
        plotly_defaults(fig_sz)
        st.plotly_chart(fig_sz, use_container_width=True)

        st.markdown("<div class='section-hdr'>Size sell-through %</div>", unsafe_allow_html=True)
        fig_spct = go.Figure(go.Bar(
            x=sdf["Size"].astype(str), y=sdf["ST"],
            marker_color=sdf["ST"].apply(st_color).tolist(),
            text=sdf["ST"].astype(str)+"%", textposition="outside",
            marker_line_width=0,
        ))
        fig_spct.update_layout(height=220, yaxis_range=[0,100], title="Size — Sell-Through %")
        plotly_defaults(fig_spct)
        st.plotly_chart(fig_spct, use_container_width=True)

    st.markdown("<div class='section-hdr'>Color × Size sell-through heatmap</div>", unsafe_allow_html=True)
    top_colors = cdf.head(12)["Color"].astype(str).tolist()
    sizes_hm   = [38, 40, 42]
    hm_data = {}
    for c in top_colors:
        for sz in sizes_hm:
            subset = filt[(filt["Color"] == c) & (filt["Size"] == sz)]
            if len(subset) and subset["Total_Invoiced"].sum() > 0:
                hm_data[(c, sz)] = round(subset["Sold"].sum() / subset["Total_Invoiced"].sum() * 100, 1)
            else:
                hm_data[(c, sz)] = None

    hm_z    = [[hm_data.get((c, sz)) for sz in sizes_hm] for c in top_colors]
    hm_text = [[f"{v}%" if v is not None else "N/A" for v in row] for row in hm_z]

    fig_hm = go.Figure(go.Heatmap(
        z=hm_z, x=[f"Size {s}" for s in sizes_hm], y=[f"#{c}" for c in top_colors],
        text=hm_text, texttemplate="%{text}",
        colorscale=[[0,"#b83232"],[0.4,"#b8730f"],[0.7,"#f5d97a"],[1,"#2d7a3a"]],
        zmin=0, zmax=100, showscale=True,
        colorbar=dict(title="ST%", thickness=12, len=0.8),
    ))
    fig_hm.update_layout(height=400, title="Color × Size Sell-Through % Heatmap (green=fast, red=slow)")
    plotly_defaults(fig_hm)
    st.plotly_chart(fig_hm, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: BRANCH ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏪 Branch Analytics":
    st.markdown("## 🏪 Branch Analytics — Which branches need attention?")

    br = data["branch"].copy()
    best_br  = br.loc[br["ST"].idxmax(), "Branch"]
    worst_br = br.loc[br[br["Inv_Qty"]>100]["ST"].idxmin(), "Branch"]

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("🏆 Best Branch",       best_br,  f"{br.loc[br['Branch']==best_br,'ST'].values[0]}% ST")
    c2.metric("💰 Top Revenue",       "Palace Road", "₹11.75L")
    c3.metric("⚠️ Weakest ST%",      worst_br, f"{br.loc[br['Branch']==worst_br,'ST'].values[0]}% ST")
    c4.metric("📦 Most Unsold",       "Kottayam", "851 units")
    c5.metric("🏪 Active Branches",  f"{len(br)}")

    st.markdown("<div class='section-hdr'>All branches — Invoiced vs Sold qty</div>", unsafe_allow_html=True)
    fig_br_all = go.Figure()
    fig_br_all.add_trace(go.Bar(name="Invoiced", y=br["Branch"], x=br["Inv_Qty"],
                                orientation="h", marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
    fig_br_all.add_trace(go.Bar(name="Sold", y=br["Branch"], x=br["Sal_Qty"],
                                orientation="h", marker_color="#2d7a3a", marker_line_width=0))
    fig_br_all.update_layout(barmode="group", height=420, title="Branch — Invoiced vs Sold")
    plotly_defaults(fig_br_all)
    st.plotly_chart(fig_br_all, use_container_width=True)

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("<div class='section-hdr'>Branch sell-through % ranking</div>", unsafe_allow_html=True)
        br_s = br.sort_values("ST", ascending=True)
        bar_colors = br_s["ST"].apply(lambda v: "#2d7a3a" if v >= 85 else "#b8730f" if v >= 70 else "#b83232").tolist()
        fig_eff = go.Figure(go.Bar(
            x=br_s["ST"], y=br_s["Branch"], orientation="h",
            marker_color=bar_colors, text=br_s["ST"].astype(str)+"%",
            textposition="outside", marker_line_width=0,
        ))
        fig_eff.update_layout(height=420, title="Branch Sell-Through %", xaxis_range=[0, 115])
        plotly_defaults(fig_eff)
        st.plotly_chart(fig_eff, use_container_width=True)

    with col_r:
        st.markdown("<div class='section-hdr'>Branch unsold qty — cash at risk</div>", unsafe_allow_html=True)
        br_u = br[br["Unsold"] > 0].sort_values("Unsold", ascending=False)
        bar_colors2 = br_u["Unsold"].apply(lambda v: "#b83232" if v > 600 else "#b8730f" if v > 300 else "#9a9891").tolist()
        fig_uns = go.Figure(go.Bar(
            x=br_u["Branch"], y=br_u["Unsold"],
            marker_color=bar_colors2, text=br_u["Unsold"].astype(int),
            textposition="outside", marker_line_width=0,
        ))
        fig_uns.update_layout(height=420, title="Unsold Units by Branch")
        plotly_defaults(fig_uns)
        st.plotly_chart(fig_uns, use_container_width=True)

    st.markdown("<div class='section-hdr'>Branch details table</div>", unsafe_allow_html=True)
    br_tbl = br[["Branch","Inv_Qty","Sal_Qty","Sal_Val","ST","Unsold"]].copy()
    br_tbl["Sal_Val"] = br_tbl["Sal_Val"].round(0).astype(int)
    br_tbl.columns = ["Branch","Invoiced","Sold","Sales Value (₹)","ST%","Unsold"]

    def color_st_br(val):
        c = "#2d7a3a" if val >= 85 else "#b8730f" if val >= 70 else "#b83232"
        return f"color:{c};font-weight:600"

    st.dataframe(
        br_tbl.style.applymap(color_st_br, subset=["ST%"]),
        use_container_width=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ACTION DECISIONS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚡ Action Decisions":
    st.markdown("## ⚡ Action Decisions — What to manufacture, stop & redistribute?")

    c1,c2,c3 = st.columns(3)
    c1.metric("✅ Reorder Colours",  "#409, #315, #442", "ST% > 80%")
    c2.metric("🛑 Stop Colours",     "#580, #357",       "ST% < 65%")
    c3.metric("📦 Redistribute",     "Kottayam → others","851 unsold")

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("### ✅ What to Manufacture / Reorder")

        st.success("""
**High priority — proven demand:**
- **Color #409** — 84.2% ST on 341 units. Top performer. Increase 30-40%.
- **Color #315** — 83.5% ST on 351 units. Safe reorder.
- **Color #442** — 81.2% ST on 489 units. High volume + high ST = reorder.
- **Color #480** — 117% ST (selling more than invoiced from old stock too). Severely undersupplied. Reorder urgently.
- **Size 38** — 70.6% ST on 14,043 units. Keep at 50%+ of production.
        """)

        st.info("""
**Next season planning:**
- Size ratio 38:40:42 = **50% : 44% : 6%** reflects actual demand. Match production to this.
- URD0180 (Color 495, Size 38) & URD0762 (Color 522, Size 42) — **100% ST** on fresh stock. Reorder both.
- Colors #336 (77.8%) and #440 (79.6%) are near best-seller threshold — scale up.
        """)

        st.markdown("### 📊 Color ST% summary for reorder decisions")
        cdf = data["color_df"].copy()
        cdf["Decision"] = cdf["ST"].apply(
            lambda v: "✅ Reorder" if v >= 80 else "⚠️ Watch" if v >= 65 else "🛑 Reduce/Stop"
        )
        cdf_show = cdf[["Color","Invoiced","Sold","ST","Decision"]].rename(
            columns={"Color":"Color #","Invoiced":"Inv","Sold":"Sold","ST":"ST%","Decision":"Action"}
        )
        def color_dec(val):
            if "Reorder" in str(val): return "color:#2d7a3a;font-weight:600"
            if "Watch"   in str(val): return "color:#b8730f;font-weight:600"
            return "color:#b83232;font-weight:600"
        st.dataframe(
            cdf_show.style.applymap(color_dec, subset=["Action"]),
            use_container_width=True, height=350
        )

    with col_r:
        st.markdown("### 🛑 What to Stop / Reduce")

        st.error("""
**Discontinue / deep discount immediately:**
- **Color #580** — 47.2% ST on 335 units. Worst high-volume performer. Do not reorder. Mark down 35%.
- **Color #357** — 62.1% ST on 433 units. Below average. Reduce 50% next season.
- **URD0052** (Color 353, 647 days old, 22.4% ST) — 52 units unsold for ~2 years. Bundle or donate.
- **URD0398** (Color 430, 627 days old, 7.1% ST) — only 3 of 42 units sold. Immediate liquidation.
- **Size 42** — 54.2% ST. Cap at ≤5-6% of production going forward.
        """)

        st.warning("""
**Watch — decide within 60 days:**
- 37 Aging SKUs (91-180 days): currently 26.4% ST. If not above 40% by Jun 2026, liquidate.
- Color #360 (63.3% ST) and #357 (62.1%): borderline. Monitor weekly before next dispatch.
        """)

        st.markdown("### 📦 Where to Redistribute Stock")
        st.warning("""
**Move stock within 30 days:**
- **Kottayam → Thiruvalla/Chalakudy**: 851 unsold, 54.1% ST. Thiruvalla (87% ST) and Chalakudy (93.1% ST) can absorb.
- **Palghat → Palace Road**: 683 unsold, 66.4% ST. Palace Road is highest revenue branch.
- **Kozhikode → Kunnamkulam**: 686 unsold, 66% ST. Kunnamkulam runs at 86% ST.
- **Increase supply to Ernakulam urgently**: 101.6% ST — they are running out of stock.
        """)

        st.markdown("### 🎯 Season Focus Summary")
        focus_data = {
            "Category":  ["Focus Colors","Avoid Colors","Focus Size","Avoid Size"],
            "Item":      ["#409, #315, #442, #440, #336","#580, #357, #360","38 & 40","42"],
            "Reason":    ["ST% ≥ 79%","ST% < 65%","97% of sales volume","Only 4%, 54% ST"],
            "Action":    ["Scale up 30-50%","Reduce or drop","Keep 94%+ of production","Cap at 5%"],
        }
        st.dataframe(pd.DataFrame(focus_data), use_container_width=True, hide_index=True)
