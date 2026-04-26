# 👗 Chaniya Analytics Dashboard

A live business analytics dashboard for apparel (chaniya / under-skirt) retail operations across 18 Kerala branches.

## 🚀 Deploy to Streamlit Cloud (Free — 5 minutes)

### Step 1 — Create a free GitHub account
Go to [github.com](https://github.com) → Sign up (free).

### Step 2 — Create a new repository
1. Click the **+** button → **New repository**
2. Name it: `chaniya-dashboard`
3. Set to **Public**
4. Click **Create repository**

### Step 3 — Upload these files to GitHub
Upload ALL files from this folder:
- `app.py`
- `requirements.txt`
- `Invoice_Data.xlsx`
- `Sales_Data.xlsx`
- `README.md`

(Click **Add file → Upload files** in GitHub)

### Step 4 — Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **New app**
4. Select your repo: `chaniya-dashboard`
5. Main file: `app.py`
6. Click **Deploy!**

✅ In 2-3 minutes your dashboard is live at:
`https://your-username-chaniya-dashboard-app-xxxxx.streamlit.app`

Share this URL with anyone in your team — no install needed!

---

## 📂 How to Update with New Weekly Data

Every week when you get new sales data:
1. Go to your GitHub repo
2. Click on `Sales_Data.xlsx` → **Delete** (or upload new file with same name)
3. Upload the new `Sales_Data.xlsx`
4. Dashboard refreshes automatically within 1 minute

**OR** — users can upload files directly inside the dashboard using the sidebar upload buttons.

---

## 📊 Dashboard Pages

| Page | Question Answered |
|------|------------------|
| 📊 Executive Summary | Overall business health |
| ⭐ Best Sellers | Which fresh SKUs to reorder |
| 🚨 Dead Stock | Where is ₹30.9L blocked |
| 🎨 Color & Size | What styles drive demand |
| 🏪 Branch Analytics | Which branches need attention |
| ⚡ Action Decisions | What to make, stop & redistribute |

---

## 🧠 Key Business Logic

### Old Stock Detection (automatic — no manual tagging)
- **First Invoice Date** per SKU is calculated from invoice data
- **Stock Age** = Today − First Invoice Date
- **Age Buckets:**
  - 🟢 Fresh = ≤ 90 days
  - 🟡 Aging = 91–180 days  
  - 🔴 Old = > 180 days
- Strategic views (Best Sellers, Color/Size) **exclude Old stock**
- Operational views (Dead Stock, Cash Blocked) **include Old stock**

### Sell-Through % = Sold Qty ÷ Invoiced Qty × 100

### Color Coding
- 🟢 Green = ST% ≥ 80% (fast moving)
- 🟡 Amber = ST% 65–79% (watch)
- 🔴 Red = ST% < 65% (slow / problem)

---

## 📞 Support
Built for: Kerala Retail Apparel Network  
Data: Jul 2024 – Apr 2026 | 18 branches | 668 SKUs | 27,908 units invoiced
