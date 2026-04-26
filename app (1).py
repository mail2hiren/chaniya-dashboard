"""
Chaniya Analytics Dashboard  v3
─────────────────────────────────
Multi-retailer · Multi-branch · 8 pages
All fixes applied:
  - Retailer derived correctly (sales 'm' col, mapped to inv via branch)
  - pandas 3.x Styler: .map() not .applymap()
  - No overlapping labels — automargin + explicit heights
  - Files persist in session (upload once, no re-upload on refresh)
  - Color filter in sidebar
  - Weekly Pulse + New Stock Tracker pages added
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os, calendar
from datetime import date

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Chaniya Analytics",
    page_icon="👗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#f5f4f0; }
[data-testid="stSidebar"]          { background:#ffffff; }
.block-container { padding-top:.8rem; padding-bottom:1rem; }
[data-testid="metric-container"] {
    background:#fff; border:0.5px solid #e5e3da;
    border-radius:9px; padding:10px 14px;
}
[data-testid="metric-container"] label { font-size:11px !important; color:#9a9891 !important; }
[data-testid="stMetricValue"] { font-size:20px !important; font-weight:600 !important; }
.sec  { font-size:11px; font-weight:600; color:#9a9891; text-transform:uppercase;
        letter-spacing:.7px; margin:14px 0 5px; }
.ibox { background:#fff7e0; border:0.5px solid #f5c87a; border-radius:8px;
        padding:9px 13px; font-size:12px; color:#6b4208; margin-bottom:10px; }
.nbox { background:#e6f1fb; border:0.5px solid #9fc6e8; border-radius:8px;
        padding:8px 12px; font-size:11px; color:#0c447c; margin-bottom:9px; }
.rdo  { background:#e8f5eb; border:0.5px solid #a3d9ae; border-radius:8px;
        padding:11px 13px; margin-bottom:8px; }
.rst  { background:#fdecea; border:0.5px solid #f5aeae; border-radius:8px;
        padding:11px 13px; margin-bottom:8px; }
.rwt  { background:#fff7e0; border:0.5px solid #f5c87a; border-radius:8px;
        padding:11px 13px; margin-bottom:8px; }
.rdo h4 { color:#1a4d22; font-size:12px; margin-bottom:5px; }
.rst h4 { color:#6e1c1c; font-size:12px; margin-bottom:5px; }
.rwt h4 { color:#6b4208; font-size:12px; margin-bottom:5px; }
.rdo li,.rst li,.rwt li { font-size:11px; margin:3px 0; color:#444; }
</style>
""", unsafe_allow_html=True)

TODAY  = pd.Timestamp(date.today())
GREEN  = "#2d7a3a"
AMBER  = "#b8730f"
RED    = "#b83232"
BLUE   = "#185FA5"

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def stc(v):
    """Return traffic-light color for a sell-through %."""
    if v >= 80: return GREEN
    if v >= 65: return AMBER
    return RED

def pc(fig, h=300, title=""):
    """Apply clean plotly theme."""
    fig.update_layout(
        height=h,
        title=dict(text=title, font_size=12, x=0, xanchor="left",
                   pad=dict(l=0, b=10)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor ="rgba(0,0,0,0)",
        margin=dict(l=4, r=20, t=48, b=4),
        font=dict(family="system-ui,sans-serif", size=11, color="#1b1a17"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font_size=10),
        hoverlabel=dict(bgcolor="#fff", font_size=11),
    )
    fig.update_xaxes(showgrid=False, tickfont_size=10,
                     title_font_size=11, automargin=True)
    fig.update_yaxes(gridcolor="#ebebeb", tickfont_size=10,
                     title_font_size=11, automargin=True)
    return fig

def sec(label):
    st.markdown(f"<div class='sec'>{label}</div>", unsafe_allow_html=True)

def ibox(txt):
    st.markdown(f"<div class='ibox'>⚠️ {txt}</div>", unsafe_allow_html=True)

def nbox(txt):
    st.markdown(f"<div class='nbox'>ℹ️ {txt}</div>", unsafe_allow_html=True)

def mkey(m):
    try:
        p = m.split("-")
        return int(p[1]) * 100 + list(calendar.month_abbr).index(p[0][:3])
    except Exception:
        return 0

def style_col(df, col, fn):
    """Styler-compatible: works with pandas ≥2.1 (.map) and older (.applymap)."""
    try:
        return df.style.map(fn, subset=[col])
    except AttributeError:
        return df.style.applymap(fn, subset=[col])

def style_cols(styler, col, fn):
    """Apply fn to a column on an existing Styler object."""
    try:
        return styler.map(fn, subset=[col])
    except AttributeError:
        return styler.applymap(fn, subset=[col])


# ─────────────────────────────────────────────────────────────────────────────
#  DATA LOADING  (cached per file identity so refresh keeps data in memory)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="⏳  Processing data…", ttl=None)
def load_data(inv_key, sal_key, inv_src, sal_src):

    inv = pd.read_excel(inv_src)
    sal = pd.read_excel(sal_src)

    # ── Invoice cleaning ─────────────────────────────────────────────────────
    inv = inv[inv["Size"] != "Size"].copy()
    for c in ["Quantity", "Price", "MRP"]:
        inv[c] = pd.to_numeric(inv[c], errors="coerce")
    inv["Invoice Date"] = pd.to_datetime(inv["Invoice Date"])
    inv["Color"] = inv["Color"].astype(str).str.strip()
    inv["Size"]  = pd.to_numeric(inv["Size"], errors="coerce")
    inv = inv[inv["Quantity"] > 0].copy()

    # ── Sales cleaning ───────────────────────────────────────────────────────
    for c in ["Quantity", "Total", "MRP"]:
        sal[c] = pd.to_numeric(sal[c], errors="coerce")
    sal["Sales Date"] = pd.to_datetime(sal["Sales Date"])

    # Retailer from sales 'm' column (e.g. "Krishna Nx Mumbai : 2576" → "Krishna Nx Mumbai")
    if "Retailer" in sal.columns:
        sal["Retailer"] = sal["Retailer"].astype(str).str.strip()
    elif "m" in sal.columns:
        sal["Retailer"] = sal["m"].astype(str).str.split(":").str[0].str.strip()
    else:
        sal["Retailer"] = "Retailer 1"

    # Map retailer to invoice rows via Branch
    br_ret_map = sal.groupby("Branch")["Retailer"].first().to_dict()
    inv["Retailer"] = inv["Branch"].map(br_ret_map).fillna("Retailer 1")

    sal_pos = sal[sal["Quantity"] > 0].copy()
    sal_pos["Week_Start"] = sal_pos["Sales Date"].dt.to_period("W").dt.start_time

    # ── Stock age per barcode ─────────────────────────────────────────────────
    fi = (
        inv.groupby("Bar Code")["Invoice Date"].min()
        .reset_index()
        .rename(columns={"Invoice Date": "First_Invoice_Date"})
    )
    fi["Stock_Age_Days"] = (TODAY - fi["First_Invoice_Date"]).dt.days
    fi["Age_Bucket"] = fi["Stock_Age_Days"].apply(
        lambda d: "🟢 Fresh (≤90d)" if d <= 90
        else "🟡 Aging (91-180d)" if d <= 180
        else "🔴 Old (>180d)"
    )

    # ── Per-barcode invoice summary ───────────────────────────────────────────
    def agg_bc(g):
        return pd.Series({
            "Total_Invoiced": g["Quantity"].sum(),
            "Invoice_Value":  (g["Price"] * g["Quantity"]).sum(),
            "MRP_Value":      (g["MRP"]   * g["Quantity"]).sum(),
            "Color":    g["Color"].iloc[0],
            "Size":     g["Size"].iloc[0],
            "Retailer": g["Retailer"].iloc[0],
        })
    bc_agg = inv.groupby("Bar Code").apply(agg_bc, include_groups=False).reset_index()

    # ── Per-barcode sales summary ─────────────────────────────────────────────
    sal_bc = (
        sal_pos.groupby("URD")
        .agg(Sold=("Quantity", "sum"), Sales_Val=("Total", "sum"))
        .reset_index()
        .rename(columns={"URD": "Bar Code"})
    )

    # ── Master SKU table ──────────────────────────────────────────────────────
    merged = (
        bc_agg
        .merge(fi[["Bar Code", "First_Invoice_Date", "Stock_Age_Days", "Age_Bucket"]],
               on="Bar Code", how="left")
        .merge(sal_bc, on="Bar Code", how="left")
    )
    merged["Sold"]      = merged["Sold"].fillna(0)
    merged["Sales_Val"] = merged["Sales_Val"].fillna(0)
    merged["Unsold"]    = (merged["Total_Invoiced"] - merged["Sold"]).clip(lower=0)
    merged["ST_Pct"]    = (
        merged["Sold"] / merged["Total_Invoiced"].replace(0, np.nan) * 100
    ).clip(0, 100).round(1).fillna(0)
    merged["Unit_MRP"]     = (merged["MRP_Value"] / merged["Total_Invoiced"].replace(0, np.nan)).fillna(0)
    merged["Cash_Blocked"] = (merged["Unsold"] * merged["Unit_MRP"]).clip(lower=0)

    # ── Branch summary ────────────────────────────────────────────────────────
    br_inv = (
        inv.groupby(["Retailer", "Branch"])
        .agg(Inv_Qty=("Quantity", "sum"),
             Inv_Val =("Price", lambda x: float((x * inv.loc[x.index, "Quantity"]).sum())))
        .reset_index()
    )
    br_sal = (
        sal_pos.groupby(["Retailer", "Branch"])
        .agg(Sal_Qty=("Quantity", "sum"), Sal_Val=("Total", "sum"))
        .reset_index()
    )
    branch = br_inv.merge(br_sal, on=["Retailer", "Branch"], how="outer").fillna(0)
    branch["ST"]     = (branch["Sal_Qty"] / branch["Inv_Qty"].replace(0, np.nan) * 100).round(1).fillna(0)
    branch["Unsold"] = (branch["Inv_Qty"] - branch["Sal_Qty"]).clip(lower=0)
    branch = branch[branch["Inv_Qty"] > 0].sort_values("Sal_Qty", ascending=False).reset_index(drop=True)

    # ── Monthly trend ─────────────────────────────────────────────────────────
    mi = inv.groupby("Month")["Quantity"].sum().to_dict()
    ms = sal_pos.groupby("Month")["Quantity"].sum().to_dict()
    all_m = sorted(set(list(mi) + list(ms)), key=mkey)
    monthly = pd.DataFrame({
        "Month":    all_m,
        "Invoiced": [int(mi.get(m, 0)) for m in all_m],
        "Sold":     [int(ms.get(m, 0)) for m in all_m],
    })

    # ── Weekly trend ──────────────────────────────────────────────────────────
    weekly = (
        sal_pos.groupby("Week_Start")["Quantity"].sum()
        .reset_index()
        .rename(columns={"Quantity": "Sold"})
        .sort_values("Week_Start")
    )

    # ── Color performance ─────────────────────────────────────────────────────
    bc_col = inv[["Bar Code", "Color"]].drop_duplicates("Bar Code")
    sc = sal_pos.merge(bc_col, left_on="URD", right_on="Bar Code", how="left")
    c_sal = sc.groupby("Color")["Quantity"].sum().reset_index().rename(columns={"Quantity": "Sold"})
    c_inv = inv.groupby("Color")["Quantity"].sum().reset_index().rename(columns={"Quantity": "Invoiced"})
    color_df = c_inv.merge(c_sal, on="Color", how="left").fillna(0)
    color_df["ST"] = (color_df["Sold"] / color_df["Invoiced"].replace(0, np.nan) * 100).round(1).fillna(0)
    color_df = color_df.sort_values("Invoiced", ascending=False).head(20).reset_index(drop=True)

    # ── Size performance ──────────────────────────────────────────────────────
    bc_sz = inv[["Bar Code", "Size"]].drop_duplicates("Bar Code")
    ss = sal_pos.merge(bc_sz, left_on="URD", right_on="Bar Code", how="left")
    s_sal = ss.groupby("Size")["Quantity"].sum().reset_index().rename(columns={"Quantity": "Sold"})
    s_inv = inv.groupby("Size")["Quantity"].sum().reset_index().rename(columns={"Quantity": "Invoiced"})
    size_df = s_inv.merge(s_sal, on="Size", how="left").fillna(0)
    size_df["ST"] = (size_df["Sold"] / size_df["Invoiced"].replace(0, np.nan) * 100).round(1).fillna(0)
    size_df = size_df[size_df["Size"].isin([38, 40, 42])].reset_index(drop=True)

    # ── Fresh velocity ────────────────────────────────────────────────────────
    fresh_bc = fi[fi["Stock_Age_Days"] <= 90].copy()
    fv_inv = (
        inv[inv["Bar Code"].isin(fresh_bc["Bar Code"])]
        .groupby("Bar Code")
        .agg(Inv=("Quantity", "sum"), Color=("Color", "first"),
             Size=("Size", "first"), inv_date=("Invoice Date", "min"))
        .reset_index()
    )
    fv_sal = (
        sal_pos[sal_pos["URD"].isin(fresh_bc["Bar Code"])]
        .groupby("URD").agg(Sold=("Quantity", "sum"))
        .reset_index().rename(columns={"URD": "Bar Code"})
    )
    fv = fv_inv.merge(fv_sal, on="Bar Code", how="left").fillna({"Sold": 0})
    fv["ST"]       = (fv["Sold"] / fv["Inv"].replace(0, np.nan) * 100).round(1).fillna(0)
    fv["Age_Days"] = (TODAY - fv["inv_date"]).dt.days
    fv["Velocity"] = (fv["Sold"] / fv["Age_Days"].replace(0, 1)).round(3)

    retailers = sorted(inv["Retailer"].dropna().unique().tolist())

    return dict(
        inv=inv, sal=sal, sal_pos=sal_pos,
        merged=merged, branch=branch,
        monthly=monthly, weekly=weekly,
        color_df=color_df, size_df=size_df,
        fresh_velocity=fv, retailers=retailers, fi=fi,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 👗 Chaniya Analytics")
    st.caption("Multi-Retailer · Multi-Branch")
    st.markdown("---")

    with st.expander("📂 Update Data Files", expanded=False):
        st.markdown(
            "<div style='font-size:11px;color:#555;'>"
            "<b>Files stay loaded for your whole session.</b><br><br>"
            "Upload here to override the default data. "
            "To update permanently, replace the Excel files on GitHub — "
            "the dashboard auto-refreshes within 1 minute.<br><br>"
            "<b>Weekly tip:</b> append new rows to your master Excel outside "
            "the app, then upload once here."
            "</div>", unsafe_allow_html=True
        )
        inv_up = st.file_uploader("Invoice Data (.xlsx)", type=["xlsx"], key="inv_up")
        sal_up = st.file_uploader("Sales Data (.xlsx)",   type=["xlsx"], key="sal_up")

    BASE    = os.path.dirname(os.path.abspath(__file__))
    inv_src = inv_up if inv_up else os.path.join(BASE, "Invoice_Data.xlsx")
    sal_src = sal_up if sal_up else os.path.join(BASE, "Sales_Data.xlsx")
    inv_key = (inv_up.name if inv_up
                else os.path.getmtime(os.path.join(BASE, "Invoice_Data.xlsx")))
    sal_key = (sal_up.name if sal_up
                else os.path.getmtime(os.path.join(BASE, "Sales_Data.xlsx")))

    data = load_data(inv_key, sal_key, inv_src, sal_src)

    st.markdown("---")
    st.markdown("### 🔍 Filters")

    sel_retailer = st.selectbox("🏬 Retailer",  ["All Retailers"] + data["retailers"])

    br_opts_df = data["branch"].copy()
    if sel_retailer != "All Retailers":
        br_opts_df = br_opts_df[br_opts_df["Retailer"] == sel_retailer]
    sel_branch = st.selectbox("🏪 Branch", ["All Branches"] + sorted(br_opts_df["Branch"].tolist()))

    sel_age = st.selectbox("📅 Stock Age",
                            ["All", "🟢 Fresh (≤90d)", "🟡 Aging (91-180d)", "🔴 Old (>180d)"])

    all_colors = sorted(data["inv"]["Color"].dropna().unique().tolist(),
                        key=lambda x: int(x) if str(x).isdigit() else 9999)
    sel_color = st.selectbox("🎨 Color", ["All Colors"] + all_colors)

    sel_size = st.selectbox("📐 Size", ["All Sizes", "38", "40", "42"])

    st.markdown("---")
    st.markdown("### 📄 Navigate")
    page = st.radio("nav", [
        "📊 Executive Summary",
        "⭐ Best Sellers",
        "🚨 Dead Stock",
        "🎨 Color & Size",
        "🏪 Branch Analytics",
        "🆕 New Stock Tracker",
        "📅 Weekly Pulse",
        "⚡ Action Decisions",
    ], label_visibility="collapsed")

    st.markdown("---")
    inv_d = data["inv"]
    st.markdown(
        f"<div style='font-size:10px;color:#9a9891;line-height:1.8;'>"
        f"Invoice: {inv_d['Invoice Date'].min().strftime('%b %Y')} – "
        f"{inv_d['Invoice Date'].max().strftime('%b %Y')}<br>"
        f"Retailers: {len(data['retailers'])}  ·  "
        f"Branches: {data['branch']['Branch'].nunique()}<br>"
        f"SKUs: {data['merged']['Bar Code'].nunique()}  ·  "
        f"Units: {int(data['merged']['Total_Invoiced'].sum()):,}<br>"
        f"<span style='color:{GREEN};'>● Live</span>  ·  "
        f"{TODAY.strftime('%d %b %Y')}"
        f"</div>", unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
#  APPLY FILTERS
# ─────────────────────────────────────────────────────────────────────────────
filt  = data["merged"].copy()
inv_f = data["inv"].copy()

if sel_retailer != "All Retailers":
    bc_r  = inv_f[inv_f["Retailer"] == sel_retailer]["Bar Code"].unique()
    filt  = filt[filt["Bar Code"].isin(bc_r)]
    inv_f = inv_f[inv_f["Retailer"] == sel_retailer]

if sel_branch != "All Branches":
    bc_b  = inv_f[inv_f["Branch"] == sel_branch]["Bar Code"].unique()
    filt  = filt[filt["Bar Code"].isin(bc_b)]
    inv_f = inv_f[inv_f["Branch"] == sel_branch]

if sel_age   != "All":        filt = filt[filt["Age_Bucket"] == sel_age]
if sel_color != "All Colors": filt = filt[filt["Color"]      == sel_color]
if sel_size  != "All Sizes":  filt = filt[filt["Size"]       == float(sel_size)]

br_f = data["branch"].copy()
if sel_retailer != "All Retailers": br_f = br_f[br_f["Retailer"] == sel_retailer]
if sel_branch   != "All Branches":  br_f = br_f[br_f["Branch"]   == sel_branch]


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 1 — EXECUTIVE SUMMARY
# ═════════════════════════════════════════════════════════════════════════════
if page == "📊 Executive Summary":
    st.markdown("## 📊 Executive Summary — What is the overall business health?")
    ibox(
        "<b>Context:</b> 583 of 667 invoiced SKUs are &gt;180 days old — "
        "stock dispatched Jul–Aug 2024 is still in the sales cycle. "
        "The overall sell-through is healthy. "
        "Fresh SKUs (≤90d) show lower ST% because they are early in their cycle — "
        "<b>expected, not alarming.</b>"
    )

    tot_inv    = int(filt["Total_Invoiced"].sum())
    tot_sold   = int(filt["Sold"].sum())
    tot_unsold = int(filt["Unsold"].sum())
    st_pct     = round(tot_sold / tot_inv * 100, 1) if tot_inv else 0
    inv_val    = round(filt["Invoice_Value"].sum() / 100000, 2)
    sal_val    = round(filt["Sales_Val"].sum() / 100000, 2)
    cash_blk   = round(filt["Cash_Blocked"].sum() / 100000, 2)
    old_cnt    = int((filt["Age_Bucket"] == "🔴 Old (>180d)").sum())
    fresh_cnt  = int((filt["Age_Bucket"] == "🟢 Fresh (≤90d)").sum())
    aging_cnt  = int((filt["Age_Bucket"] == "🟡 Aging (91-180d)").sum())

    c = st.columns(8)
    c[0].metric("📦 Invoiced Qty",  f"{tot_inv:,}")
    c[1].metric("💰 Invoice Value", f"₹{inv_val}L")
    c[2].metric("✅ Sold Qty",       f"{tot_sold:,}")
    c[3].metric("💵 Sales Value",    f"₹{sal_val}L")
    c[4].metric("📈 Sell-Through",   f"{st_pct}%",
                "✓ Above 75% target" if st_pct >= 75 else "⚠ Below 75% target")
    c[5].metric("📦 Unsold Qty",     f"{tot_unsold:,}")
    c[6].metric("🔒 Cash Blocked",   f"₹{cash_blk}L")
    c[7].metric("⚠️ Old SKUs",       f"{old_cnt}")

    sec("Monthly trend — Invoice vs Sales quantity")
    mdf = data["monthly"]
    fig_t = go.Figure()
    fig_t.add_trace(go.Bar(name="Invoiced", x=mdf["Month"], y=mdf["Invoiced"],
                           marker_color="rgba(24,95,165,0.55)", marker_line_width=0))
    fig_t.add_trace(go.Bar(name="Sold",     x=mdf["Month"], y=mdf["Sold"],
                           marker_color=GREEN, marker_line_width=0))
    fig_t.update_layout(barmode="group")
    pc(fig_t, 290, "Monthly Invoice vs Sold Quantity")
    st.plotly_chart(fig_t, use_container_width=True)

    cl, cr = st.columns(2)
    with cl:
        sec("Stock age breakdown")
        age_df = filt["Age_Bucket"].value_counts().reset_index()
        age_df.columns = ["Bucket", "Count"]
        fig_age = px.pie(
            age_df, names="Bucket", values="Count", hole=0.58,
            color="Bucket",
            color_discrete_map={"🟢 Fresh (≤90d)": GREEN,
                                "🟡 Aging (91-180d)": AMBER,
                                "🔴 Old (>180d)": RED},
        )
        fig_age.update_traces(textposition="outside", textfont_size=10)
        pc(fig_age, 290,
           f"SKUs by Age  |  🟢 {fresh_cnt}  🟡 {aging_cnt}  🔴 {old_cnt}")
        st.plotly_chart(fig_age, use_container_width=True)

    with cr:
        sec("Top 10 best sellers — fresh stock only (≤90d)")
        fresh = filt[filt["Age_Bucket"] == "🟢 Fresh (≤90d)"]
        t10 = (fresh[fresh["Total_Invoiced"] >= 3]
               .sort_values("ST_Pct", ascending=False).head(10).copy())
        if len(t10):
            t10["Lbl"] = (t10["Bar Code"] + "  C#" +
                          t10["Color"].astype(str) + "  Sz" +
                          t10["Size"].fillna(0).astype(int).astype(str))
            fig_top = go.Figure(go.Bar(
                x=t10["ST_Pct"], y=t10["Lbl"], orientation="h",
                marker_color=t10["ST_Pct"].apply(stc).tolist(),
                text=t10["ST_Pct"].astype(str) + "%",
                textposition="outside", marker_line_width=0,
            ))
            fig_top.update_layout(xaxis_range=[0, 125])
            pc(fig_top, 290, "Top Fresh SKUs by Sell-Through %")
            st.plotly_chart(fig_top, use_container_width=True)
        else:
            st.info("No fresh SKUs matching current filters.")


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 2 — BEST SELLERS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "⭐ Best Sellers":
    st.markdown("## ⭐ Best Sellers — Which SKUs to reorder now?")
    nbox("Old stock (&gt;180d) is excluded. Analysis based on fresh demand only.")

    cdf       = data["color_df"]
    fresh_all = filt[filt["Age_Bucket"] == "🟢 Fresh (≤90d)"].copy()
    top_st    = round(fresh_all["ST_Pct"].max(), 1) if len(fresh_all) else 0
    best_c    = cdf.loc[cdf["ST"].idxmax(), "Color"] if len(cdf) else "—"
    best_cst  = round(cdf["ST"].max(), 1)            if len(cdf) else 0

    c = st.columns(4)
    c[0].metric("🏆 Top Fresh ST%",   f"{top_st}%")
    c[1].metric("🆕 Fresh SKUs",       f"{len(fresh_all)}")
    c[2].metric("🎨 Best Color ST%",   f"#{best_c}", f"{best_cst}%")
    c[3].metric("📐 Best Size",         "38",         "70.6% ST")

    sec("Top fresh SKUs by sell-through % — old stock excluded")
    tf = (fresh_all[fresh_all["Total_Invoiced"] >= 3]
          .sort_values("ST_Pct", ascending=False).head(15).copy())
    if len(tf):
        tf["Lbl"] = (tf["Bar Code"] + "  |  Color #" +
                     tf["Color"].astype(str) + "  |  Size " +
                     tf["Size"].fillna(0).astype(int).astype(str))
        fig_f = go.Figure(go.Bar(
            x=tf["ST_Pct"], y=tf["Lbl"], orientation="h",
            marker_color=tf["ST_Pct"].apply(stc).tolist(),
            text=tf["ST_Pct"].astype(str) + "%",
            textposition="outside", marker_line_width=0,
            customdata=tf[["Total_Invoiced","Sold"]].values,
            hovertemplate=("<b>%{y}</b><br>ST%: %{x}<br>"
                           "Invoiced: %{customdata[0]}  Sold: %{customdata[1]}"
                           "<extra></extra>"),
        ))
        fig_f.update_layout(xaxis_range=[0, 125])
        pc(fig_f, max(320, len(tf) * 32), "Fresh SKUs — ST%  (🟢≥80%  🟡65-79%  🔴<65%)")
        st.plotly_chart(fig_f, use_container_width=True)
    else:
        st.info("No fresh SKUs with ≥3 units invoiced in current filter.")

    cl, cr = st.columns(2)
    with cl:
        sec("Color codes — invoiced vs sold (top 20)")
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(name="Invoiced",
                               x=cdf["Color"].astype(str), y=cdf["Invoiced"],
                               marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
        fig_c.add_trace(go.Bar(name="Sold",
                               x=cdf["Color"].astype(str), y=cdf["Sold"],
                               marker_color=GREEN, marker_line_width=0))
        fig_c.update_layout(barmode="group")
        pc(fig_c, 310, "Color Code — Invoiced vs Sold")
        st.plotly_chart(fig_c, use_container_width=True)

    with cr:
        sec("Size performance — invoiced vs sold")
        sdf = data["size_df"]
        sz_lbl = sdf["Size"].fillna(0).astype(int).astype(str)
        fig_s = go.Figure()
        fig_s.add_trace(go.Bar(name="Invoiced", x=sz_lbl, y=sdf["Invoiced"],
                               marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
        fig_s.add_trace(go.Bar(name="Sold",     x=sz_lbl, y=sdf["Sold"],
                               marker_color=GREEN, marker_line_width=0))
        max_y = sdf["Invoiced"].max()
        for _, row in sdf.iterrows():
            fig_s.add_annotation(
                x=str(int(row["Size"])), y=row["Invoiced"] + max_y * 0.04,
                text=f"{row['ST']}% ST", showarrow=False,
                font=dict(size=11, color="#333"),
            )
        fig_s.update_layout(barmode="group",
                             yaxis_range=[0, max_y * 1.15])
        pc(fig_s, 310, "Size 38 / 40 / 42 — Invoiced vs Sold")
        st.plotly_chart(fig_s, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 3 — DEAD STOCK
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🚨 Dead Stock":
    st.markdown("## 🚨 Dead Stock — Where is cash blocked?")

    old   = filt[filt["Age_Bucket"] == "🔴 Old (>180d)"]
    aging = filt[filt["Age_Bucket"] == "🟡 Aging (91-180d)"]

    c = st.columns(4)
    c[0].metric("🔴 Old SKUs (>180d)",  f"{len(old)}")
    c[1].metric("💰 Cash Blocked @MRP", f"₹{round(filt['Cash_Blocked'].sum()/100000,2)}L")
    c[2].metric("🟡 Aging SKUs",         f"{len(aging)}")
    c[3].metric("0% ST SKUs",            f"{int((filt['ST_Pct']==0).sum())}")

    cl, cr = st.columns(2)
    with cl:
        sec("Unsold qty by branch")
        bru = br_f[br_f["Unsold"] > 0].sort_values("Unsold", ascending=False)
        if len(bru):
            fig_bu = go.Figure(go.Bar(
                x=bru["Branch"], y=bru["Unsold"],
                marker_color=bru["Unsold"].apply(
                    lambda v: RED if v > 600 else AMBER if v > 300 else "#888"
                ).tolist(),
                marker_line_width=0,
                text=bru["Unsold"].astype(int), textposition="outside",
            ))
            pc(fig_bu, 300, "Unsold Units by Branch")
            st.plotly_chart(fig_bu, use_container_width=True)

    with cr:
        sec("Branch ST% vs unsold (bubble = supply size)")
        bsc = br_f[br_f["Inv_Qty"] > 0].copy()
        if len(bsc):
            fig_sc = px.scatter(
                bsc, x="ST", y="Unsold", text="Branch", size="Inv_Qty",
                color="ST", color_continuous_scale=[RED, AMBER, GREEN],
                range_color=[50, 100],
                labels={"ST": "Sell-Through %", "Unsold": "Unsold Units"},
            )
            fig_sc.update_traces(textposition="top center",
                                  textfont_size=9, marker_line_width=0)
            fig_sc.update_coloraxes(showscale=False)
            pc(fig_sc, 300, "ST% vs Unsold Qty")
            st.plotly_chart(fig_sc, use_container_width=True)

    sec("Dead stock register — ST% < 30%, oldest first")
    dead = (
        filt[filt["ST_Pct"] < 30]
        .sort_values(["Stock_Age_Days","ST_Pct"], ascending=[False,True])
        .head(30)
        [["Bar Code","Color","Size","Stock_Age_Days","Age_Bucket",
          "Total_Invoiced","Sold","ST_Pct","Cash_Blocked"]]
        .copy()
    )
    dead["Cash_Blocked"] = dead["Cash_Blocked"].round(0).astype(int)
    dead["Size"] = dead["Size"].fillna(0).astype(int)
    dead = dead.rename(columns={
        "Bar Code":"SKU","Stock_Age_Days":"Age (Days)","Age_Bucket":"Stage",
        "Total_Invoiced":"Invoiced","ST_Pct":"ST%","Cash_Blocked":"Cash Blocked (₹)",
    })

    # pandas 3-safe styling
    base = dead.style
    base = style_cols(base, "ST%",
        lambda v: f"color:{RED if v<10 else AMBER if v<20 else '#666'};font-weight:600")
    base = style_cols(base, "Age (Days)",
        lambda v: f"color:{RED if v>365 else AMBER if v>180 else '#666'}")
    st.dataframe(base, use_container_width=True, height=420)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 4 — COLOR & SIZE
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🎨 Color & Size":
    st.markdown("## 🎨 Color & Size Trends — What styles drive demand?")

    cdf  = data["color_df"].copy()
    sdf  = data["size_df"].copy()
    valid = cdf[cdf["ST"] < 110]

    if len(cdf):
        best_c  = cdf.loc[cdf["ST"].idxmax()]
        worst_c = valid.loc[valid["ST"].idxmin()] if len(valid) else cdf.iloc[-1]
        c = st.columns(4)
        c[0].metric("🏆 Best Color (ST%)", f"#{best_c['Color']}",  f"{best_c['ST']}%")
        c[1].metric("🏆 Best Size",        "Size 38",              "70.6% ST")
        c[2].metric("⚠️ Worst Color",      f"#{worst_c['Color']}", f"{worst_c['ST']}%")
        c[3].metric("⚠️ Weakest Size",     "Size 42",              "54.2% ST")

    cl, cr = st.columns(2)
    with cl:
        sec("Color sell-through % — sorted worst → best")
        cdf_s = cdf.sort_values("ST").copy()
        cdf_s["ST_d"] = cdf_s["ST"].clip(0, 100)
        fig_cst = go.Figure(go.Bar(
            x=cdf_s["ST_d"], y=cdf_s["Color"].astype(str), orientation="h",
            marker_color=cdf_s["ST_d"].apply(stc).tolist(),
            text=cdf_s["ST"].astype(str) + "%",
            textposition="outside", marker_line_width=0,
            customdata=cdf_s[["Invoiced","Sold"]].values,
            hovertemplate=("Color #%{y}<br>ST: %{x}%<br>"
                           "Inv: %{customdata[0]}  Sold: %{customdata[1]}"
                           "<extra></extra>"),
        ))
        fig_cst.update_layout(xaxis_range=[0, 125])
        pc(fig_cst, max(360, len(cdf_s) * 22), "Color Code — Sell-Through %")
        st.plotly_chart(fig_cst, use_container_width=True)

    with cr:
        sec("Size — invoiced vs sold")
        sz_lbl = sdf["Size"].fillna(0).astype(int).astype(str)
        fig_sz = go.Figure()
        fig_sz.add_trace(go.Bar(name="Invoiced", x=sz_lbl, y=sdf["Invoiced"],
                                marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
        fig_sz.add_trace(go.Bar(name="Sold",     x=sz_lbl, y=sdf["Sold"],
                                marker_color=GREEN, marker_line_width=0))
        fig_sz.update_layout(barmode="group")
        pc(fig_sz, 210, "Size — Invoiced vs Sold")
        st.plotly_chart(fig_sz, use_container_width=True)

        sec("Size sell-through %")
        fig_sp = go.Figure(go.Bar(
            x=sz_lbl, y=sdf["ST"],
            marker_color=sdf["ST"].apply(stc).tolist(),
            text=sdf["ST"].astype(str) + "%",
            textposition="outside", marker_line_width=0,
        ))
        fig_sp.update_layout(yaxis_range=[0, 105])
        pc(fig_sp, 195, "Size Sell-Through %")
        st.plotly_chart(fig_sp, use_container_width=True)

    sec("Color × Size sell-through heatmap — top 12 colors by volume")
    top_cols = cdf.head(12)["Color"].astype(str).tolist()
    hm_z, hm_t = [], []
    for c_code in top_cols:
        rz, rt = [], []
        for sz in [38, 40, 42]:
            sub = filt[(filt["Color"] == c_code) & (filt["Size"] == float(sz))]
            if len(sub) and sub["Total_Invoiced"].sum() > 0:
                v = round(sub["Sold"].sum() / sub["Total_Invoiced"].sum() * 100, 1)
                rz.append(v); rt.append(f"{v}%")
            else:
                rz.append(None); rt.append("N/A")
        hm_z.append(rz); hm_t.append(rt)

    fig_hm = go.Figure(go.Heatmap(
        z=hm_z, x=["Size 38","Size 40","Size 42"],
        y=[f"Color #{c}" for c in top_cols],
        text=hm_t, texttemplate="%{text}",
        colorscale=[[0, RED],[0.4, AMBER],[0.7,"#f5d97a"],[1, GREEN]],
        zmin=0, zmax=100, showscale=True,
        colorbar=dict(title="ST%", thickness=12, len=0.8,
                      tickvals=[0,25,50,75,100],
                      ticktext=["0%","25%","50%","75%","100%"]),
    ))
    pc(fig_hm, 400, "Color × Size Sell-Through % Heatmap  (🟢 fast → 🔴 slow)")
    st.plotly_chart(fig_hm, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 5 — BRANCH ANALYTICS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🏪 Branch Analytics":
    st.markdown("## 🏪 Branch Analytics — Which branches need attention?")

    brv = br_f[br_f["Inv_Qty"] > 0].copy()
    large = brv[brv["Inv_Qty"] > 100]
    best_r  = brv.loc[brv["ST"].idxmax()]       if len(brv)   else None
    worst_r = large.loc[large["ST"].idxmin()]    if len(large) else None
    top_rev = brv.sort_values("Sal_Val", ascending=False).iloc[0] if len(brv) else None

    c = st.columns(5)
    c[0].metric("🏆 Best ST%",       best_r["Branch"]  if best_r  else "—",
                f"{best_r['ST']}%"   if best_r  else "")
    c[1].metric("💰 Top Revenue",    top_rev["Branch"] if top_rev else "—",
                f"₹{round(float(top_rev['Sal_Val'])/100000,2)}L" if top_rev else "")
    c[2].metric("⚠️ Weakest ST%",   worst_r["Branch"] if worst_r else "—",
                f"{worst_r['ST']}%" if worst_r else "")
    c[3].metric("📦 Total Unsold",   f"{int(brv['Unsold'].sum()):,}")
    c[4].metric("🏪 Active Branches",f"{len(brv)}")

    sec("All branches — invoiced vs sold qty")
    fig_all = go.Figure()
    fig_all.add_trace(go.Bar(name="Invoiced", y=brv["Branch"], x=brv["Inv_Qty"],
                             orientation="h",
                             marker_color="rgba(24,95,165,0.45)", marker_line_width=0))
    fig_all.add_trace(go.Bar(name="Sold",     y=brv["Branch"], x=brv["Sal_Qty"],
                             orientation="h",
                             marker_color=GREEN, marker_line_width=0))
    fig_all.update_layout(barmode="group")
    pc(fig_all, max(320, len(brv) * 28), "Branch — Invoiced vs Sold")
    st.plotly_chart(fig_all, use_container_width=True)

    cl, cr = st.columns(2)
    with cl:
        sec("Branch sell-through % ranking")
        brs = brv.sort_values("ST")
        fig_eff = go.Figure(go.Bar(
            x=brs["ST"], y=brs["Branch"], orientation="h",
            marker_color=brs["ST"].apply(
                lambda v: GREEN if v >= 85 else AMBER if v >= 70 else RED
            ).tolist(),
            text=brs["ST"].astype(str) + "%",
            textposition="outside", marker_line_width=0,
        ))
        fig_eff.update_layout(xaxis_range=[0, 125])
        pc(fig_eff, max(300, len(brs) * 27), "Branch Sell-Through %")
        st.plotly_chart(fig_eff, use_container_width=True)

    with cr:
        sec("Branch unsold qty — cash at risk")
        bru = brv[brv["Unsold"] > 0].sort_values("Unsold", ascending=False)
        if len(bru):
            fig_un = go.Figure(go.Bar(
                x=bru["Branch"], y=bru["Unsold"],
                marker_color=bru["Unsold"].apply(
                    lambda v: RED if v > 600 else AMBER if v > 300 else "#888"
                ).tolist(),
                text=bru["Unsold"].astype(int),
                textposition="outside", marker_line_width=0,
            ))
            pc(fig_un, max(300, len(bru) * 24), "Unsold Units by Branch")
            st.plotly_chart(fig_un, use_container_width=True)

    sec("Branch details table")
    tbl = brv[["Retailer","Branch","Inv_Qty","Sal_Qty","Sal_Val","ST","Unsold"]].copy()
    tbl["Sal_Val"] = tbl["Sal_Val"].round(0).astype(int)
    tbl = tbl.rename(columns={"Inv_Qty":"Invoiced","Sal_Qty":"Sold",
                               "Sal_Val":"Sales Val (₹)","ST":"ST%"})
    base = tbl.style
    base = style_cols(base, "ST%",
        lambda v: f"color:{GREEN if v>=85 else AMBER if v>=70 else RED};font-weight:600")
    st.dataframe(base, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 6 — NEW STOCK TRACKER
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🆕 New Stock Tracker":
    st.markdown("## 🆕 New Stock Tracker — How is freshly invoiced stock selling?")
    nbox("SKUs invoiced in the last 90 days. Velocity shows how fast each SKU is selling "
         "— catch fast movers before they run out, and stalling SKUs before they age.")

    fv = data["fresh_velocity"].copy()
    if sel_color != "All Colors": fv = fv[fv["Color"] == sel_color]
    if sel_size  != "All Sizes":  fv = fv[fv["Size"]  == float(sel_size)]

    tv = fv.sort_values("Velocity", ascending=False).iloc[0] if len(fv) else None

    c = st.columns(4)
    c[0].metric("🆕 Fresh SKUs",       f"{len(fv)}")
    c[1].metric("📦 Invoiced (fresh)",  f"{int(fv['Inv'].sum())}")
    c[2].metric("✅ Sold (fresh)",       f"{int(fv['Sold'].sum())}")
    c[3].metric("🚀 Fastest SKU",       tv["Bar Code"] if tv is not None else "—",
                f"{tv['Velocity']:.3f} u/day" if tv is not None else "")

    cl, cr = st.columns(2)
    with cl:
        sec("Sell-through % — early signal")
        fv_st = fv.sort_values("ST", ascending=False).copy()
        fv_st["Lbl"] = (fv_st["Bar Code"] + "  C#" +
                        fv_st["Color"].astype(str) + "  Sz" +
                        fv_st["Size"].fillna(0).astype(int).astype(str))
        if len(fv_st):
            fig_fst = go.Figure(go.Bar(
                x=fv_st["ST"], y=fv_st["Lbl"], orientation="h",
                marker_color=fv_st["ST"].apply(stc).tolist(),
                text=fv_st["ST"].astype(str) + "%",
                textposition="outside", marker_line_width=0,
            ))
            fig_fst.update_layout(xaxis_range=[0, 125])
            pc(fig_fst, max(300, len(fv_st) * 27), "Fresh SKUs — Sell-Through %")
            st.plotly_chart(fig_fst, use_container_width=True)

    with cr:
        sec("Sales velocity — units sold per day since invoiced")
        fv_vel = fv.sort_values("Velocity", ascending=False).copy()
        fv_vel["Lbl"] = (fv_vel["Bar Code"] + "  C#" +
                         fv_vel["Color"].astype(str) + "  Sz" +
                         fv_vel["Size"].fillna(0).astype(int).astype(str))
        if len(fv_vel):
            fig_vel = go.Figure(go.Bar(
                x=fv_vel["Velocity"], y=fv_vel["Lbl"], orientation="h",
                marker_color=BLUE,
                text=fv_vel["Velocity"].round(3).astype(str),
                textposition="outside", marker_line_width=0,
            ))
            pc(fig_vel, max(300, len(fv_vel) * 27), "Sales Velocity — Units per Day")
            st.plotly_chart(fig_vel, use_container_width=True)

    sec("Full fresh stock table")
    fvt = fv.copy()
    fvt["Size"]     = fvt["Size"].fillna(0).astype(int)
    fvt["inv_date"] = fvt["inv_date"].dt.strftime("%d %b %Y")
    fvt = fvt.rename(columns={"Bar Code":"SKU","inv_date":"Inv Date","Inv":"Invoiced",
                                "ST":"ST%","Age_Days":"Age (Days)","Velocity":"Vel (u/day)"})
    fvt = fvt[["SKU","Color","Size","Inv Date","Invoiced","Sold","ST%","Age (Days)","Vel (u/day)"]]
    base = fvt.sort_values("ST%", ascending=False).style
    base = style_cols(base, "ST%",
        lambda v: f"color:{GREEN if v>=80 else AMBER if v>=50 else RED};font-weight:600")
    st.dataframe(base, use_container_width=True)

    fast  = fv[fv["Velocity"] >= fv["Velocity"].quantile(0.75)] if len(fv) >= 4 else fv
    stall = fv[(fv["Age_Days"] >= 30) & (fv["ST"] < 20)]
    cl2, cr2 = st.columns(2)
    with cl2:
        if len(fast):
            st.success("**🚀 Fast movers — top quartile by velocity:**\n\n" +
                       "\n".join([f"- **{r['Bar Code']}** C#{r['Color']} Sz{int(r['Size'])} — "
                                  f"{r['Velocity']:.3f} u/day · {r['ST']}% ST in {r['Age_Days']}d"
                                  for _, r in fast.iterrows()]))
    with cr2:
        if len(stall):
            st.warning("**⚠️ Stalling — <20% ST after 30+ days:**\n\n" +
                       "\n".join([f"- **{r['Bar Code']}** C#{r['Color']} Sz{int(r['Size'])} — "
                                  f"{r['ST']}% ST in {r['Age_Days']}d. Review placement/pricing."
                                  for _, r in stall.iterrows()]))


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 7 — WEEKLY PULSE
# ═════════════════════════════════════════════════════════════════════════════
elif page == "📅 Weekly Pulse":
    st.markdown("## 📅 Weekly Pulse — How is business moving week on week?")
    nbox("Week-on-week sales movement. Spot acceleration, slowdowns, and seasonal spikes early.")

    wdf = data["weekly"].copy()
    if len(wdf) >= 2:
        lw  = int(wdf.iloc[-1]["Sold"])
        pw  = int(wdf.iloc[-2]["Sold"])
        wop = round((lw - pw) / pw * 100, 1) if pw else 0
        a4  = round(wdf.tail(4)["Sold"].mean(), 0)
        c = st.columns(4)
        c[0].metric("📅 Last Week",   f"{lw:,}",           f"{wop:+.1f}% vs prev")
        c[1].metric("📅 Prev Week",   f"{pw:,}")
        c[2].metric("📊 4-Week Avg",  f"{a4:,.0f}")
        c[3].metric("📈 12-Week Tot", f"{int(wdf.tail(12)['Sold'].sum()):,}")

    sec("Weekly sales trend — last 26 weeks")
    wp = wdf.tail(26).copy()
    wp["Lbl"] = wp["Week_Start"].dt.strftime("W%V %d %b")
    wp["MA4"] = wp["Sold"].rolling(4, min_periods=1).mean().round(0)

    fig_w = go.Figure()
    fig_w.add_trace(go.Bar(x=wp["Lbl"], y=wp["Sold"],
                           marker_color=BLUE, marker_line_width=0,
                           name="Weekly Sold", opacity=0.75))
    fig_w.add_trace(go.Scatter(x=wp["Lbl"], y=wp["MA4"],
                               mode="lines", name="4-week avg",
                               line=dict(color=GREEN, width=2.5, dash="dot")))
    pc(fig_w, 300, "Weekly Sales (bars) + 4-Week Moving Avg (dotted)")
    st.plotly_chart(fig_w, use_container_width=True)

    sec("Week-on-week change")
    wp["WoW"] = wp["Sold"].diff()
    fig_wow = go.Figure(go.Bar(
        x=wp["Lbl"].iloc[1:], y=wp["WoW"].iloc[1:],
        marker_color=wp["WoW"].iloc[1:].apply(
            lambda v: GREEN if v > 0 else RED if v < 0 else AMBER
        ).tolist(),
        marker_line_width=0,
        text=wp["WoW"].iloc[1:].fillna(0).astype(int).astype(str),
        textposition="outside",
    ))
    fig_wow.add_hline(y=0, line_color="#ccc", line_width=1)
    pc(fig_wow, 240, "Week-on-Week Change (🟢 growth  🔴 decline)")
    st.plotly_chart(fig_wow, use_container_width=True)

    cl, cr = st.columns(2)
    with cl:
        sec("Weekly sales — top 6 branches (last 12 weeks)")
        sp = data["sal_pos"].copy()
        sp["Lbl"] = sp["Week_Start"].dt.strftime("%d %b")
        top6 = (data["branch"].sort_values("Sal_Qty", ascending=False)
                .head(6)["Branch"].tolist())
        last12 = sorted(sp["Week_Start"].unique())[-12:]
        sbwk = (sp[sp["Branch"].isin(top6) & sp["Week_Start"].isin(last12)]
                .groupby(["Lbl","Branch"])["Quantity"].sum().reset_index())
        if len(sbwk):
            fig_bwk = px.line(sbwk, x="Lbl", y="Quantity", color="Branch",
                              markers=True, labels={"Quantity":"Units","Lbl":"Week"})
            fig_bwk.update_traces(line_width=2, marker_size=5)
            pc(fig_bwk, 280, "Weekly Sales by Top 6 Branches")
            st.plotly_chart(fig_bwk, use_container_width=True)

    with cr:
        sec("Weekly returns & return rate %")
        sa = data["sal"].copy()
        sa["Week_Start"] = sa["Sales Date"].dt.to_period("W").dt.start_time
        sa["Lbl"]        = sa["Week_Start"].dt.strftime("%d %b")
        last12_dt = sorted(data["sal_pos"]["Week_Start"].unique())[-12:]
        saf  = sa[sa["Week_Start"].isin(last12_dt)]
        rtwk = (saf[saf["Quantity"] < 0].groupby("Lbl")["Quantity"].sum().abs()
                .reset_index().rename(columns={"Quantity":"Returns"}))
        poswk= (saf[saf["Quantity"] > 0].groupby("Lbl")["Quantity"].sum()
                .reset_index().rename(columns={"Quantity":"Sold"}))
        rm   = poswk.merge(rtwk, on="Lbl", how="left").fillna(0)
        rm["Ret%"] = (rm["Returns"] / rm["Sold"].replace(0, np.nan) * 100).round(1).fillna(0)

        fig_ret = go.Figure()
        fig_ret.add_trace(go.Bar(x=rm["Lbl"], y=rm["Returns"],
                                 marker_color=RED, marker_line_width=0, name="Returns"))
        fig_ret.add_trace(go.Scatter(x=rm["Lbl"], y=rm["Ret%"],
                                     mode="lines+markers", name="Return Rate %",
                                     yaxis="y2",
                                     line=dict(color=AMBER, width=2)))
        fig_ret.update_layout(
            yaxis2=dict(overlaying="y", side="right",
                        ticksuffix="%", showgrid=False)
        )
        pc(fig_ret, 280, "Weekly Returns & Return Rate %")
        st.plotly_chart(fig_ret, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 8 — ACTION DECISIONS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "⚡ Action Decisions":
    st.markdown("## ⚡ Action Decisions — What to manufacture, stop & redistribute?")

    cdf = data["color_df"].copy()
    brr = data["branch"].copy()
    fv  = data["fresh_velocity"].copy()

    reorder_c = cdf[cdf["ST"] >= 80]
    stop_c    = cdf[(cdf["ST"] > 0) & (cdf["ST"] < 65)]
    watch_c   = cdf[(cdf["ST"] >= 65) & (cdf["ST"] < 80)]
    redist_br = brr[brr["Unsold"] > 400].sort_values("Unsold", ascending=False)
    fast_new  = fv[fv["Velocity"] >= fv["Velocity"].quantile(0.75)] if len(fv) >= 4 else fv
    stall_new = fv[(fv["Age_Days"] >= 30) & (fv["ST"] < 20)]

    c = st.columns(3)
    c[0].metric("✅ Reorder Colors",  f"{len(reorder_c)} colors",  "ST% ≥ 80%")
    c[1].metric("🛑 Stop / Reduce",   f"{len(stop_c)} colors",    "ST% < 65%")
    c[2].metric("📦 Redistribute",    f"{len(redist_br)} branches","Unsold > 400 units")

    sec("Priority action matrix")
    cl, cr = st.columns(2)

    # ── Left column ───────────────────────────────────────────────────────────
    with cl:
        ro_items = "".join([
            f"<li><b>Color #{r['Color']}</b> — {r['ST']}% ST on "
            f"{int(r['Invoiced'])} units. Reorder confidence: HIGH ✓</li>"
            for _, r in reorder_c.sort_values("ST", ascending=False).iterrows()
        ])
        st.markdown(
            f"<div class='rdo'><h4>✅ MANUFACTURE / REORDER — Proven demand</h4><ul>"
            f"{ro_items}"
            f"<li><b>Color #480</b> — 117% ST (selling old stock too). "
            f"<b>Undersupplied. Reorder urgently.</b></li>"
            f"<li><b>Size 38</b> — 70.6% ST on 14,043 units. ≥50% of production.</li>"
            f"<li><b>Size 40</b> — 69.5% ST on 12,247 units. ~44% of production.</li>"
            f"</ul></div>", unsafe_allow_html=True
        )

        wt_items = "".join([
            f"<li><b>Color #{r['Color']}</b> — {r['ST']}% ST. Monitor before reordering.</li>"
            for _, r in watch_c.sort_values("ST", ascending=False).iterrows()
        ])
        st.markdown(
            f"<div class='rwt'><h4>⚠️ WATCH — Decide in 60 days</h4><ul>"
            f"{wt_items}"
            f"<li><b>37 Aging SKUs</b> — 26.4% avg ST. If below 40% by Jun 2026, liquidate.</li>"
            f"</ul></div>", unsafe_allow_html=True
        )

        if len(fast_new):
            fn_items = "".join([
                f"<li><b>{r['Bar Code']}</b> C#{r['Color']} Sz{int(r['Size'])} — "
                f"{r['Velocity']:.3f} u/day · {r['ST']}% ST in {r['Age_Days']}d</li>"
                for _, r in fast_new.iterrows()
            ])
            st.markdown(
                f"<div class='rdo'><h4>🚀 ACCELERATE — New stock selling fast</h4>"
                f"<ul>{fn_items}</ul></div>", unsafe_allow_html=True
            )

    # ── Right column ──────────────────────────────────────────────────────────
    with cr:
        st_items = "".join([
            f"<li><b>Color #{r['Color']}</b> — {r['ST']}% ST on {int(r['Invoiced'])} units. "
            f"Do not reorder. Mark down 30-40%.</li>"
            for _, r in stop_c.sort_values("ST").iterrows()
        ])
        st.markdown(
            f"<div class='rst'><h4>🛑 STOP / DEEP DISCOUNT</h4><ul>"
            f"{st_items}"
            f"<li><b>Size 42</b> — 54.2% ST. Cap at ≤5% of next production.</li>"
            f"<li><b>URD0052</b> (647 days, 22.4% ST) — bundle or donate.</li>"
            f"<li><b>URD0398</b> (627 days, 7.1% ST) — immediate liquidation.</li>"
            f"</ul></div>", unsafe_allow_html=True
        )

        rd_items = "".join([
            f"<li><b>{r['Branch']}</b> — {int(r['Unsold'])} unsold, {r['ST']}% ST. "
            f"Redistribute to high-demand branches.</li>"
            for _, r in redist_br.iterrows()
        ])
        st.markdown(
            f"<div class='rwt'><h4>📦 REDISTRIBUTE — Move within 30 days</h4><ul>"
            f"{rd_items}"
            f"<li><b>Ernakulam</b> — 101.6% ST (running out!). Increase supply urgently.</li>"
            f"</ul></div>", unsafe_allow_html=True
        )

        if len(stall_new):
            sn_items = "".join([
                f"<li><b>{r['Bar Code']}</b> C#{r['Color']} Sz{int(r['Size'])} — "
                f"{r['ST']}% ST in {r['Age_Days']}d. Review pricing/placement.</li>"
                for _, r in stall_new.iterrows()
            ])
            st.markdown(
                f"<div class='rst'><h4>🔴 STALLING NEW STOCK — Act before it ages</h4>"
                f"<ul>{sn_items}</ul></div>", unsafe_allow_html=True
            )

    sec("Color action matrix — reorder / watch / stop zones")
    cdf_a = cdf.copy()
    cdf_a["Action"] = cdf_a["ST"].apply(
        lambda v: "✅ Reorder" if v >= 80 else "⚠️ Watch" if v >= 65 else "🛑 Stop/Reduce"
    )
    cdf_a["ST_d"] = cdf_a["ST"].clip(0, 100)
    fig_act = px.bar(
        cdf_a.sort_values("Invoiced", ascending=False),
        x="Color", y="ST_d", color="Action",
        color_discrete_map={"✅ Reorder": GREEN, "⚠️ Watch": AMBER, "🛑 Stop/Reduce": RED},
        text="ST_d",
        hover_data={"Invoiced": True, "Sold": True},
        labels={"ST_d": "Sell-Through %", "Color": "Color Code"},
    )
    fig_act.add_hline(y=80, line_dash="dot", line_color=GREEN,
                      annotation_text="80% reorder threshold",
                      annotation_position="top right", annotation_font_size=10)
    fig_act.add_hline(y=65, line_dash="dot", line_color=AMBER,
                      annotation_text="65% watch threshold",
                      annotation_position="top right", annotation_font_size=10)
    fig_act.update_traces(texttemplate="%{text}%", textposition="outside",
                          marker_line_width=0)
    fig_act.update_layout(yaxis_range=[0, 125])
    pc(fig_act, 350, "Color Code Action Matrix")
    st.plotly_chart(fig_act, use_container_width=True)

    sec("Season focus — next production priorities")
    focus = pd.DataFrame({
        "Category": ["Colors","Colors","Colors","Colors",
                     "Sizes","Sizes","Sizes"],
        "Item": [
            "Reorder: #" + ", #".join(reorder_c["Color"].tolist()),
            "Undersupplied: #480 (117% ST)",
            "Watch: #" + ", #".join(watch_c["Color"].tolist()),
            "Stop: #" + ", #".join(stop_c["Color"].tolist()),
            "Size 38 — 70.6% ST",
            "Size 40 — 69.5% ST",
            "Size 42 — 54.2% ST",
        ],
        "Action": [
            "Scale up 30-50% in next production",
            "Reorder urgently — stock running out",
            "Monitor weekly, decide in 60 days",
            "Do not reorder. Mark down current stock.",
            "Keep at ≥50% of production",
            "Keep at ~44% of production",
            "Cap at ≤5% of production",
        ],
        "Priority": [
            "🔴 Urgent","🔴 Urgent","🟡 Monitor","🔴 Urgent",
            "🟢 Confirmed","🟢 Confirmed","🔴 Reduce"
        ],
    })
    st.dataframe(focus, use_container_width=True, hide_index=True)
