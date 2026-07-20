# streamlit_app.py
# NRI ITR Wizard — FY 2025-26 (AY 2026-27) — OLD REGIME (+ New Regime quick check)
# Guides NRI (Middle East) through rent, interest, capital gains, and credits,
# shows refund/payable, a quick Old-vs-New regime comparison, and lets the user
# email the summary/Excel report to themselves or their CA.

import datetime as dt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from typing import Dict, Any, Tuple
from io import BytesIO

import streamlit as st
import pandas as pd

FY_LABEL = "FY 2025-26"
AY_LABEL = "AY 2026-27"

STEPS = [
    "1) Profile & Notes",
    "2) House Property (Rent)",
    "3) Interest",
    "4) Capital Gains",
    "5) Other Income & Deductions",
    "6) Tax Credits",
    "7) Regime Comparison",
    "8) Summary, Download & Email",
]

st.set_page_config(page_title="NRI ITR Wizard · FY 2025-26", page_icon="📑", layout="wide")

# ---------- Styling ----------
def inject_css():
    st.markdown("""
    <style>
        :root {
            --navy: #0B2B4C;
            --navy-light: #123A63;
            --gold: #C9A227;
            --bg: #F6F7F9;
        }
        .stApp { background-color: var(--bg); }

        /* Header banner */
        .nri-header {
            background: linear-gradient(120deg, var(--navy) 0%, var(--navy-light) 100%);
            padding: 22px 28px;
            border-radius: 14px;
            color: #FFFFFF;
            margin-bottom: 18px;
            box-shadow: 0 4px 14px rgba(11,43,76,0.20);
        }
        .nri-header h1 { margin: 0; font-size: 1.55rem; font-weight: 700; }
        .nri-header p { margin: 6px 0 0 0; font-size: 0.92rem; color: #D8E1EC; }
        .nri-header .badge {
            display: inline-block; background: var(--gold); color: #1A1A1A;
            padding: 2px 10px; border-radius: 999px; font-size: 0.75rem;
            font-weight: 700; margin-right: 8px;
        }

        /* Metric cards */
        div[data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #E4E8EE;
            border-left: 4px solid var(--gold);
            border-radius: 10px;
            padding: 14px 16px 10px 16px;
            box-shadow: 0 1px 4px rgba(16,24,40,0.05);
        }
        div[data-testid="stMetricLabel"] { font-weight: 600; color: #4A5568; }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: var(--navy);
        }
        section[data-testid="stSidebar"] * { color: #EDF1F7 !important; }
        section[data-testid="stSidebar"] .stRadio label span {
            font-size: 0.92rem;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label {
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 6px 8px;
            margin-bottom: 4px;
        }

        /* Buttons */
        .stButton>button, .stDownloadButton>button {
            background-color: var(--navy);
            color: white;
            border-radius: 8px;
            border: none;
            font-weight: 600;
        }
        .stButton>button:hover, .stDownloadButton>button:hover {
            background-color: var(--gold);
            color: #1A1A1A;
        }

        /* Section headers */
        h1, h2, h3 { color: var(--navy); }

        .verdict-pay { color: #B42318; font-weight: 700; }
        .verdict-refund { color: #067647; font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

inject_css()

# ---------- Helpers ----------
def inr(x: float) -> str:
    return f"₹{x:,.2f}"

def old_regime_basic_tax_slab(ti: float) -> float:
    # Old regime for individuals (NRI): 0–2.5L Nil; 2.5–5L 5%; 5–10L 20%; >10L 30%.
    if ti <= 250000:
        return 0.0
    if ti <= 500000:
        return 0.05 * (ti - 250000)
    if ti <= 1000000:
        return 12500 + 0.20 * (ti - 500000)
    return 112500 + 0.30 * (ti - 1000000)

def new_regime_basic_tax_slab(ti: float) -> float:
    # New regime FY 2025-26 (Budget 2025): 0-4L Nil; 4-8L 5%; 8-12L 10%;
    # 12-16L 15%; 16-20L 20%; 20-24L 25%; >24L 30%.
    # NOTE: Section 87A rebate (nil tax up to ~12L for residents) does NOT apply to NRIs.
    if ti <= 400000:
        return 0.0
    if ti <= 800000:
        return 0.05 * (ti - 400000)
    if ti <= 1200000:
        return 20000 + 0.10 * (ti - 800000)
    if ti <= 1600000:
        return 60000 + 0.15 * (ti - 1200000)
    if ti <= 2000000:
        return 120000 + 0.20 * (ti - 1600000)
    if ti <= 2400000:
        return 200000 + 0.25 * (ti - 2000000)
    return 300000 + 0.30 * (ti - 2400000)

def surcharge_rate(total_income: float, regime: str = "old") -> float:
    # 0 up to 50L; 10% (50L–1Cr); 15% (1–2Cr); 25% (2–5Cr); 37% (>5Cr, OLD REGIME ONLY)
    # New regime: the 37% band was removed (Budget 2023) — surcharge caps at 25%.
    if total_income <= 5_000_000: return 0.0
    if total_income <= 10_000_000: return 0.10
    if total_income <= 20_000_000: return 0.15
    if total_income <= 50_000_000: return 0.25
    return 0.25 if regime == "new" else 0.37

def apply_surcharge_with_caps(tax_slab: float,
                              tax_111A: float,
                              tax_112A: float,
                              tax_112: float,
                              total_income: float,
                              regime: str = "old") -> Tuple[float, Dict[str, float]]:
    sr = surcharge_rate(total_income, regime)
    surcharge_slab = tax_slab * sr
    capped_sr = min(sr, 0.15)  # cap at 15% for 111A/112/112A
    surcharge_111A = tax_111A * capped_sr
    surcharge_112A = tax_112A * capped_sr
    surcharge_112  = tax_112  * capped_sr
    total = surcharge_slab + surcharge_111A + surcharge_112A + surcharge_112
    return total, {
        "surcharge_rate_overall": sr,
        "surcharge_on_slab": surcharge_slab,
        "surcharge_on_111A_capped": surcharge_111A,
        "surcharge_on_112A_capped": surcharge_112A,
        "surcharge_on_112_capped": surcharge_112,
        "surcharge_total": total,
    }

def send_email_with_attachment(smtp_host: str, smtp_port: int, sender_email: str,
                                app_password: str, recipient_email: str, subject: str,
                                body: str, attachment_bytes: bytes, attachment_name: str) -> Tuple[bool, str]:
    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={attachment_name}")
        msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(sender_email, app_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        return False, f"Email failed: {e}"

# ---------- Header banner ----------
st.markdown(f"""
<div class="nri-header">
    <span class="badge">{FY_LABEL}</span><span class="badge">{AY_LABEL}</span><span class="badge">Old Regime</span>
    <h1>📑 NRI ITR Wizard</h1>
    <p>Estimate Indian income tax for NRIs (Middle East) — house property, interest, capital gains, credits, and a quick Old-vs-New regime check.</p>
</div>
""", unsafe_allow_html=True)

# ---------- Sidebar navigation ----------
st.sidebar.title("🧭 Navigation")
st.sidebar.markdown(f"**{FY_LABEL} / {AY_LABEL}**")
step = st.sidebar.radio(
    "Steps",
    STEPS,
    index=0,
    help="Move through each section and fill values; your results update at the end."
)
step_idx = STEPS.index(step) + 1
st.sidebar.progress(step_idx / len(STEPS))
st.sidebar.caption(f"Step {step_idx} of {len(STEPS)}")

# ---------- Input state containers ----------
if "inputs" not in st.session_state:
    st.session_state.inputs = {
        "gross_rent": 0.0,
        "municipal_taxes": 0.0,
        "home_loan_interest": 0.0,

        "nro_savings_interest": 0.0,
        "nro_term_interest": 0.0,
        "nre_interest": 0.0,

        "stcg_eq": 0.0,         # listed equity/Equity MF STCG (111A) @20%
        "ltcg_eq": 0.0,         # listed equity/Equity MF LTCG (112A) @12.5%, 1.25L exemption
        "stcg_other_slab": 0.0, # slab-taxed STCG (e.g., property <24m)
        "ltcg_20": 0.0,         # other LTCG @20% (112)
        "ltcg_10": 0.0,         # other LTCG @10% (112)

        "other_slab_income": 0.0,
        "other_deductions": 0.0,   # 80C/80D/80G etc. (80TTA auto below)

        "tds_total": 0.0,
        "advance_tax": 0.0,
    }

X = st.session_state.inputs

# ---------- Step 1: Profile & Notes ----------
if step.startswith("1"):
    st.header("1) Profile & Notes")
    col1, col2 = st.columns([2,1])
    with col1:
        st.markdown("""
- This tool estimates **Indian income tax for an NRI** under the **Old Regime** for **FY 2025-26 (AY 2026-27)**, with a quick **New Regime comparison** (Step 7).
- It prompts for **house property (rent)**, **interest** (NRO/NRE), **capital gains**, and **tax credits (TDS/Advance tax)**.
- **80TTA** on NRO **savings** interest up to ₹10,000 is auto-applied. **NRE/FCNR interest** is treated **exempt** in India.
- **Equity capital gains**: STCG (111A) at a flat **20%**, LTCG (112A) at a flat **12.5%** with a **₹1,25,000** annual exemption — the entire FY 2025-26 falls after the 23-Jul-2024 rate change, so no date-wise split is needed this year.
- **Surcharge** bands + **4% cess** applied; surcharge on **111A/112/112A** capped at **15%**. New regime additionally caps overall surcharge at **25%** (no 37% band).
- **Section 87A rebate does NOT apply to NRIs** (resident-only relief) — not applied anywhere in this tool, under either regime.
- Old Regime slab rates and surcharge bands are **unchanged from FY 2024-25** — no Budget 2025/2026 change affects them.
- Governing law for this filing is still the **Income-tax Act, 1961**. The new **Income-tax Act, 2025** (and Income-tax Rules, 2026) applies only from **FY 2026-27 (AY 2027-28)** onward.
- **Due dates:** 31-Jul-2026 (ITR-1/ITR-2, no audit); 31-Aug-2026 (ITR-3/ITR-4, no audit).

> **Disclaimer:** Educational estimator only. For complex cases (marginal relief, DTAA, multiple properties, indexing nuances), please consult a CA.
        """)
    with col2:
        st.info("💡 Enter **0** where not applicable.\nYou can revisit steps any time — your inputs are kept in session.")
        st.warning("⚠️ Since NRIs get **no 87A rebate**, the New Regime's headline 'nil up to ₹12L' does **not** apply to you — see Step 7.")

# ---------- Step 2: House Property ----------
if step.startswith("2"):
    st.header("2) House Property (Let-out in India)")
    X["gross_rent"] = max(0.0, float(st.number_input("Gross annual rent received (₹)", value=float(X["gross_rent"]), step=1000.0)))
    X["municipal_taxes"] = max(0.0, float(st.number_input("Municipal taxes actually paid during FY (₹)", value=float(X["municipal_taxes"]), step=1000.0)))
    nav = max(0.0, X["gross_rent"] - X["municipal_taxes"])
    std_ded = 0.30 * nav
    X["home_loan_interest"] = max(0.0, float(st.number_input("Home loan interest paid during FY (₹)", value=float(X["home_loan_interest"]), step=1000.0)))
    income_hp = nav - std_ded - X["home_loan_interest"]
    allowed_setoff = income_hp if income_hp >= 0 else max(income_hp, -200000.0)
    carry_forward = -(income_hp - allowed_setoff) if income_hp < 0 else 0.0

    st.subheader("Computation")
    colA, colB, colC, colD = st.columns(4)
    colA.metric("Net Annual Value (NAV)", inr(nav))
    colB.metric("Std. Deduction (30% of NAV)", inr(std_ded))
    colC.metric("HP Income (can be loss)", inr(income_hp))
    colD.metric("Loss Set-off this year (cap ₹2L)", inr(allowed_setoff if allowed_setoff<0 else 0.0))
    if carry_forward > 0:
        st.caption(f"Unabsorbed house property loss to carry forward: **{inr(carry_forward)}** (can be set off only against HP in future years).")

# ---------- Step 3: Interest ----------
if step.startswith("3"):
    st.header("3) Interest")
    X["nro_savings_interest"] = max(0.0, float(st.number_input("NRO SAVINGS account interest (₹)", value=float(X["nro_savings_interest"]), step=1000.0)))
    X["nro_term_interest"] = max(0.0, float(st.number_input("NRO TERM/FD interest (₹)", value=float(X["nro_term_interest"]), step=1000.0)))
    X["nre_interest"] = max(0.0, float(st.number_input("NRE/FCNR interest (for info; exempt in India) (₹)", value=float(X["nre_interest"]), step=1000.0)))

    tta = min(10000.0, X["nro_savings_interest"])
    taxable_interest = max(0.0, (X["nro_savings_interest"] + X["nro_term_interest"]) - tta)

    st.subheader("Computation")
    col1, col2, col3 = st.columns(3)
    col1.metric("80TTA on NRO savings (max ₹10,000)", inr(tta))
    col2.metric("Taxable Interest (NRO)", inr(taxable_interest))
    col3.metric("NRE/FCNR interest (exempt)", inr(X["nre_interest"]))

# ---------- Step 4: Capital Gains ----------
if step.startswith("4"):
    st.header("4) Capital Gains")
    st.markdown("**Equity/STT-paid** (listed equity & equity MF, FY 2025-26 rates apply uniformly — no date split needed):")
    X["stcg_eq"] = max(0.0, float(st.number_input("STCG on listed equity/Equity MF — Sec 111A @20% (₹)", value=float(X["stcg_eq"]), step=1000.0)))
    X["ltcg_eq"] = max(0.0, float(st.number_input("LTCG on listed equity/Equity MF — Sec 112A @12.5% (₹)", value=float(X["ltcg_eq"]), step=1000.0)))

    st.markdown("**Other capital gains:**")
    X["stcg_other_slab"] = max(0.0, float(st.number_input("Other STCG taxed at **slab** (₹)", value=float(X["stcg_other_slab"]), step=1000.0)))
    X["ltcg_20"] = max(0.0, float(st.number_input("Other LTCG **@20%** (₹)", value=float(X["ltcg_20"]), step=1000.0)))
    X["ltcg_10"] = max(0.0, float(st.number_input("Other LTCG **@10%** (₹)", value=float(X["ltcg_10"]), step=1000.0)))

    # Compute preview taxes for display
    tax_stcg_eq = 0.20 * X["stcg_eq"]
    exemption = min(125000.0, X["ltcg_eq"])
    ltcg_eq_taxable = max(0.0, X["ltcg_eq"] - exemption)
    tax_ltcg_eq = 0.125 * ltcg_eq_taxable

    col1, col2, col3 = st.columns(3)
    col1.metric("Tax STCG Eq (111A) @20%", inr(tax_stcg_eq))
    col2.metric("Eq LTCG exemption applied (max ₹1,25,000)", inr(exemption))
    col3.metric("Tax LTCG Eq (112A) @12.5%", inr(tax_ltcg_eq))

# ---------- Step 5: Other Income & Deductions ----------
if step.startswith("5"):
    st.header("5) Other Income & Deductions")
    X["other_slab_income"] = max(0.0, float(st.number_input("Any OTHER slab-taxed income (e.g., salary/consulting in India) (₹)", value=float(X["other_slab_income"]), step=1000.0)))
    X["other_deductions"] = max(0.0, float(st.number_input("Total other deductions (80C/80D/80G etc.) **EXCLUDING 80TTA** (₹)", value=float(X["other_deductions"]), step=1000.0)))
    st.caption("Note: Chapter VIA deductions (80C/80D/80G etc.) are available under the **Old Regime only**. The New Regime comparison in Step 7 ignores this input, consistent with law.")

# ---------- Step 6: Tax Credits ----------
if step.startswith("6"):
    st.header("6) Tax Credits")
    X["tds_total"] = max(0.0, float(st.number_input("TDS/TCS credit as per Form 26AS/AIS (₹)", value=float(X["tds_total"]), step=1000.0)))
    X["advance_tax"] = max(0.0, float(st.number_input("Advance/Self-Assessment Tax already paid (₹)", value=float(X["advance_tax"]), step=1000.0)))

# ---------- Computation Core ----------
def compute_summary(X: Dict[str, float]) -> Dict[str, Any]:
    # House property set-off
    nav = max(0.0, X["gross_rent"] - X["municipal_taxes"])
    std_ded = 0.30 * nav
    income_hp = nav - std_ded - X["home_loan_interest"]
    hp_setoff = income_hp if income_hp >= 0 else max(income_hp, -200000.0)
    carryforward_loss = -(income_hp - hp_setoff) if income_hp < 0 else 0.0

    # Interest
    tta = min(10000.0, X["nro_savings_interest"])
    taxable_interest = max(0.0, (X["nro_savings_interest"] + X["nro_term_interest"]) - tta)

    # Capital gains taxes
    tax_stcg_eq = 0.20 * X["stcg_eq"]
    exemption = min(125000.0, X["ltcg_eq"])
    ltcg_eq_taxable = max(0.0, X["ltcg_eq"] - exemption)
    tax_ltcg_eq = 0.125 * ltcg_eq_taxable

    tax_ltcg_20 = 0.20 * X["ltcg_20"]
    tax_ltcg_10 = 0.10 * X["ltcg_10"]

    # Slab-taxable income (sum of positive components; include negative HP set-off within cap)
    slab_income_components = taxable_interest + X["stcg_other_slab"] + X["other_slab_income"]
    if hp_setoff < 0:
        slab_income_components = max(0.0, slab_income_components + hp_setoff)
    else:
        slab_income_components += hp_setoff

    # Deductions (excl. 80TTA)
    slab_after_deductions = max(0.0, slab_income_components - X["other_deductions"])

    # Slab tax
    tax_on_slab = old_regime_basic_tax_slab(slab_after_deductions)

    # Special rate tax
    tax_111A = tax_stcg_eq
    tax_112A = tax_ltcg_eq
    tax_112 = tax_ltcg_20 + tax_ltcg_10

    # Total income for surcharge purposes (approximate; non-negative sums)
    total_income = 0.0
    total_income += max(0.0, income_hp)
    total_income += taxable_interest
    total_income += X["stcg_other_slab"]
    total_income += X["stcg_eq"]
    total_income += X["ltcg_eq"]
    total_income += X["ltcg_20"] + X["ltcg_10"]
    total_income += X["other_slab_income"]
    total_income = max(0.0, total_income - X["other_deductions"])

    surcharge, surcharge_break = apply_surcharge_with_caps(tax_on_slab, tax_111A, tax_112A, tax_112, total_income, regime="old")
    tax_before_cess = tax_on_slab + tax_111A + tax_112A + tax_112 + surcharge
    cess = 0.04 * tax_before_cess
    total_tax = tax_before_cess + cess

    taxes_paid = X["tds_total"] + X["advance_tax"]
    net_payable = total_tax - taxes_paid

    return {
        "meta": {"fy": FY_LABEL, "ay": AY_LABEL, "generated_at": dt.datetime.now().isoformat()},
        "house_property": {
            "gross_rent": X["gross_rent"],
            "municipal_taxes": X["municipal_taxes"],
            "nav": nav,
            "std_deduction_30pct": std_ded,
            "home_loan_interest": X["home_loan_interest"],
            "income_from_house_property": income_hp,
            "allowed_setoff": hp_setoff,
            "loss_carryforward_not_used": carryforward_loss,
        },
        "interest": {
            "nro_savings_interest": X["nro_savings_interest"],
            "nro_term_interest": X["nro_term_interest"],
            "nre_interest_exempt": X["nre_interest"],
            "sec80TTA_deduction": tta,
            "taxable_interest_total": taxable_interest,
        },
        "capital_gains_inputs": {
            "stcg_eq_111A": X["stcg_eq"],
            "ltcg_eq_112A": X["ltcg_eq"],
            "ltcg_eq_exemption_applied": exemption,
            "ltcg_eq_taxable": ltcg_eq_taxable,
            "stcg_other_slab": X["stcg_other_slab"],
            "ltcg_20": X["ltcg_20"],
            "ltcg_10": X["ltcg_10"],
        },
        "capital_gains_taxes": {
            "tax_111A_stcg_total": tax_111A,
            "tax_112A_ltcg_total": tax_112A,
            "tax_112_other_ltcg_total": tax_112,
        },
        "slab_income_before_deductions": slab_income_components,
        "chapter_VIA_other_deductions": X["other_deductions"],
        "slab_income_after_deductions": slab_after_deductions,
        "tax_on_slab_income": tax_on_slab,
        "surcharge_breakdown": surcharge_break,
        "cess_4pct": cess,
        "total_tax_liability": total_tax,
        "credits": {"tds_tcs": X["tds_total"], "advance_tax": X["advance_tax"]},
        "net_payable_positive_else_refund_negative": net_payable,
        "_internal": {
            "tax_111A": tax_111A, "tax_112A": tax_112A, "tax_112": tax_112,
            "slab_income_components": slab_income_components,
        }
    }

def compute_new_regime_estimate(X: Dict[str, float], internals: Dict[str, float]) -> Dict[str, float]:
    """Approximate New Regime tax for comparison: same special-rate CG taxes (111A/112A/112
    are unchanged across regimes), but slab income taxed on New Regime slabs WITHOUT
    Chapter VIA deductions (not allowed under New Regime), and surcharge capped at 25%
    (no 37% band). No 87A rebate for NRIs under either regime."""
    slab_income = internals["slab_income_components"]  # before other_deductions, as New Regime disallows them
    tax_on_slab_new = new_regime_basic_tax_slab(max(0.0, slab_income))

    tax_111A = internals["tax_111A"]
    tax_112A = internals["tax_112A"]
    tax_112 = internals["tax_112"]

    total_income_new = max(0.0, slab_income) + X["stcg_eq"] + X["ltcg_eq"] + X["ltcg_20"] + X["ltcg_10"]

    surcharge, _ = apply_surcharge_with_caps(tax_on_slab_new, tax_111A, tax_112A, tax_112, total_income_new, regime="new")
    tax_before_cess = tax_on_slab_new + tax_111A + tax_112A + tax_112 + surcharge
    cess = 0.04 * tax_before_cess
    total_tax_new = tax_before_cess + cess

    return {
        "tax_on_slab_new": tax_on_slab_new,
        "surcharge_new": surcharge,
        "cess_new": cess,
        "total_tax_new": total_tax_new,
    }

# ---------- Step 7: Regime Comparison ----------
if step.startswith("7"):
    st.header("7) Regime Comparison (Quick Check)")
    st.caption("Approximate side-by-side using your inputs so far. Capital gains rates (111A/112A/112) are identical under both regimes; the difference is in slab tax, deduction eligibility, and surcharge cap.")

    summary = compute_summary(X)
    new_est = compute_new_regime_estimate(X, summary["_internal"])

    old_total = summary["total_tax_liability"]
    new_total = new_est["total_tax_new"]
    diff = old_total - new_total

    col1, col2, col3 = st.columns(3)
    col1.metric("Old Regime — Total Tax", inr(old_total))
    col2.metric("New Regime — Total Tax (est.)", inr(new_total))
    if diff > 0:
        col3.metric("New Regime saves you", inr(diff))
    elif diff < 0:
        col3.metric("Old Regime saves you", inr(abs(diff)))
    else:
        col3.metric("Difference", inr(0.0))

    st.markdown("#### Why they differ")
    diff_table = pd.DataFrame([
        {"Item": "Slab tax on non-CG income", "Old Regime": inr(summary["tax_on_slab_income"]), "New Regime": inr(new_est["tax_on_slab_new"])},
        {"Item": "Chapter VIA deductions (80C/80D etc.)", "Old Regime": inr(X["other_deductions"]), "New Regime": inr(0.0) + " (not allowed)"},
        {"Item": "Surcharge (highest band)", "Old Regime": "up to 37%", "New Regime": "capped at 25%"},
        {"Item": "Section 87A rebate (NRI)", "Old Regime": "Not applicable", "New Regime": "Not applicable"},
    ])
    st.table(diff_table)

    st.warning("⚠️ This is a simplified comparison for direction-setting only — it does not re-derive every deduction/exemption difference (e.g., standard deduction on salary, HRA). Confirm with a CA before choosing a regime, especially near ITR filing deadline.")

# ---------- Step 8: Summary, Download & Email ----------
if step.startswith("8"):
    st.header("8) Summary, Download & Email")
    summary = compute_summary(X)

    # Key metrics
    net = summary["net_payable_positive_else_refund_negative"]
    total_tax = summary["total_tax_liability"]
    tds = summary["credits"]["tds_tcs"]
    adv = summary["credits"]["advance_tax"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tax Liability", inr(total_tax))
    col2.metric("Taxes Already Paid (TDS+Advance)", inr(tds + adv))
    col3.metric("Amount Payable" if net >= 0 else "Estimated Refund", inr(abs(net)))

    if net >= 0:
        st.markdown(f"<p class='verdict-pay'>⚠️ Estimated amount payable: {inr(net)}. Consider paying Self-Assessment Tax before filing to avoid interest under Sec 234A/B/C.</p>", unsafe_allow_html=True)
    else:
        st.markdown(f"<p class='verdict-refund'>✅ Estimated refund: {inr(abs(net))}.</p>", unsafe_allow_html=True)

    # Compact on-screen table
    st.markdown("#### Compact Summary")
    simple = {
        "Total Tax Liability": total_tax,
        "TDS/TCS": tds,
        "Advance/SAT": adv,
        "Net Payable (+) / Refund (-)": net,
    }
    df_simple = pd.DataFrame(list(simple.items()), columns=["Metric", "Amount (₹)"])
    st.table(df_simple.assign(**{"Amount (₹)": df_simple["Amount (₹)"].map(inr)}))

    # Detailed JSON (as reference)
    with st.expander("🔍 Detailed JSON (full computation trail)"):
        st.json({k: v for k, v in summary.items() if k != "_internal"})

    # Build Excel with multiple sheets
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # Summary sheet (keep numbers numeric for Excel formatting)
        df_simple.to_excel(writer, index=False, sheet_name="Summary")

        # House Property
        (pd.DataFrame([summary["house_property"]]).T
           .reset_index()
           .rename(columns={"index": "Field", 0: "Value"})
           .to_excel(writer, index=False, sheet_name="House Property"))

        # Interest
        (pd.DataFrame([summary["interest"]]).T
           .reset_index()
           .rename(columns={"index": "Field", 0: "Value"})
           .to_excel(writer, index=False, sheet_name="Interest"))

        # Capital Gains (inputs & taxes)
        (pd.DataFrame([summary["capital_gains_inputs"]]).T
           .reset_index()
           .rename(columns={"index": "Field", 0: "Value"})
           .to_excel(writer, index=False, sheet_name="Cap Gains Inputs"))

        (pd.DataFrame([summary["capital_gains_taxes"]]).T
           .reset_index()
           .rename(columns={"index": "Field", 0: "Value"})
           .to_excel(writer, index=False, sheet_name="Cap Gains Taxes"))

        # Computation highlights
        comp = {
            "Slab income before deductions": summary["slab_income_before_deductions"],
            "Deductions (other)": summary["chapter_VIA_other_deductions"],
            "Slab income after deductions": summary["slab_income_after_deductions"],
            "Tax on slab income": summary["tax_on_slab_income"],
            "Cess 4%": summary["cess_4pct"],
        }
        (pd.DataFrame(list(comp.items()), columns=["Field", "Value"])
           .to_excel(writer, index=False, sheet_name="Computation"))

        # Light formatting
        wb = writer.book
        money = wb.add_format({"num_format": "#,##0.00"})
        ws_sum = writer.sheets["Summary"]
        ws_sum.set_column("A:A", 34)          # Metric
        ws_sum.set_column("B:B", 20, money)   # Amount

        # Auto-fit-ish columns for other sheets
        for name, ws in writer.sheets.items():
            if name == "Summary":
                continue
            ws.set_column("A:A", 38)
            ws.set_column("B:B", 24)

    data = output.getvalue()
    excel_filename = "nri_itr_summary_fy2025_26.xlsx"

    st.download_button(
        "⬇️ Download Excel (FY 2025-26)",
        data=data,
        file_name=excel_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # ---------- Email the report ----------
    st.markdown("---")
    st.subheader("📧 Get this report by email")

    gmail_sender = st.secrets.get("gmail_sender", None) if hasattr(st, "secrets") else None
    gmail_app_password = st.secrets.get("gmail_app_password", None) if hasattr(st, "secrets") else None
    sender_configured = bool(gmail_sender and gmail_app_password)

    if not sender_configured:
        st.info(
            "📮 Email sending isn't configured yet. The app owner needs to add `gmail_sender` and "
            "`gmail_app_password` to `.streamlit/secrets.toml` (or the Streamlit Cloud Secrets manager) "
            "— generate the App Password at myaccount.google.com/apppasswords with 2FA enabled."
        )

    ecol1, ecol2 = st.columns([3, 1])
    with ecol1:
        user_email = st.text_input("Your email address", key="user_email", placeholder="you@example.com")
    with ecol2:
        st.write("")  # vertical spacer to align button with input
        send_clicked = st.button("Send me the report", key="send_email_btn", disabled=not sender_configured)

    if send_clicked:
        if not user_email or "@" not in user_email:
            st.error("Please enter a valid email address.")
        else:
            subject = f"Your NRI ITR Summary — {FY_LABEL} ({AY_LABEL})"
            body = (
                f"Hi,\n\nPlease find attached your NRI ITR estimate for {FY_LABEL} ({AY_LABEL}).\n"
                f"Total tax liability: {inr(total_tax)}\n"
                f"{'Amount payable' if net >= 0 else 'Estimated refund'}: {inr(abs(net))}\n\n"
                f"This is an educational estimate — please cross-check before filing.\n\nRegards"
            )
            with st.spinner("Sending your report..."):
                ok, msg = send_email_with_attachment(
                    "smtp.gmail.com", 587, gmail_sender, gmail_app_password,
                    user_email, subject, body, data, excel_filename
                )
            if ok:
                st.success(f"✅ Sent! Check {user_email} for your report.")
            else:
                st.error(f"❌ {msg}")

st.sidebar.markdown("---")
st.sidebar.caption("This tool assumes **Old Regime** (Income-tax Act, 1961 — still governs FY 2025-26), applies 80TTA on NRO savings, equity CG at flat 111A/112A rates (20% / 12.5%, ₹1.25L exemption), and surcharge caps on special-rate gains. Health & Education Cess at 4%. Section 87A rebate not applied (NRIs are not eligible).")
st.sidebar.caption(f"Due dates: 31-Jul-2026 (ITR-1/ITR-2), 31-Aug-2026 (ITR-3/ITR-4, no audit). Always cross-check with your Form 26AS/AIS & ITR utility. For edge cases, consult a CA.")
