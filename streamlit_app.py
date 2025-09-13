# streamlit_app.py
# NRI ITR Wizard — FY 2024-25 (AY 2025-26) — OLD REGIME
# Guides NRI (Middle East) through rent, interest, capital gains, and credits, then shows refund/payable.

import datetime as dt
from typing import Dict, Any, Tuple
from io import BytesIO

import streamlit as st
import pandas as pd

FY_LABEL = "FY 2024-25"
AY_LABEL = "AY 2025-26"

st.set_page_config(page_title="NRI ITR Wizard (FY 2024-25)", page_icon="📑", layout="wide")

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

def surcharge_rate(total_income: float) -> float:
    # 0 up to 50L; 10% (50L–1Cr); 15% (1–2Cr); 25% (2–5Cr); 37% (>5Cr)
    if total_income <= 5_000_000: return 0.0
    if total_income <= 10_000_000: return 0.10
    if total_income <= 20_000_000: return 0.15
    if total_income <= 50_000_000: return 0.25
    return 0.37

def apply_surcharge_with_caps(tax_slab: float,
                              tax_111A: float,
                              tax_112A: float,
                              tax_112: float,
                              total_income: float) -> Tuple[float, Dict[str, float]]:
    sr = surcharge_rate(total_income)
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

# ---------- Sidebar navigation ----------
st.sidebar.title("NRI ITR Wizard")
st.sidebar.markdown(f"**{FY_LABEL} / {AY_LABEL}** · Old Regime")
step = st.sidebar.radio(
    "Steps",
    [
        "1) Profile & Notes",
        "2) House Property (Rent)",
        "3) Interest",
        "4) Capital Gains",
        "5) Other Income & Deductions",
        "6) Tax Credits",
        "7) Summary & Download",
    ],
    index=0,
    help="Move through each section and fill values; your results update at the end."
)

# ---------- Input state containers ----------
if "inputs" not in st.session_state:
    st.session_state.inputs = {
        "gross_rent": 0.0,
        "municipal_taxes": 0.0,
        "home_loan_interest": 0.0,

        "nro_savings_interest": 0.0,
        "nro_term_interest": 0.0,
        "nre_interest": 0.0,

        "stcg_eq_pre": 0.0,     # before 23-Jul-2024 @15%
        "stcg_eq_post": 0.0,    # on/after 23-Jul-2024 @20%
        "ltcg_eq_pre": 0.0,     # before 23-Jul-2024 @10% (112A)
        "ltcg_eq_post": 0.0,    # on/after 23-Jul-2024 @12.5% (112A)
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
- This tool estimates **Indian income tax for an NRI** under the **Old Regime** for **FY 2024-25 (AY 2025-26)**.
- It prompts for **house property (rent)**, **interest** (NRO/NRE), **capital gains**, and **tax credits (TDS/Advance tax)**.
- **80TTA** on NRO **savings** interest up to ₹10,000 is auto-applied. **NRE/FCNR interest** is treated **exempt** in India.
- **Equity CG changes from 23-Jul-2024** handled via date-wise inputs.
- **Surcharge** bands + **4% cess** applied; surcharge on **111A/112/112A** capped at **15%**.

> **Disclaimer:** Educational estimator only. For complex cases (marginal relief, DTAA, multiple properties, indexing nuances), please consult a CA.
        """)
    with col2:
        st.info("Tip: Enter **0** where not applicable.\nYou can revisit steps any time.")

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
    st.markdown("**Equity/STT-paid** (enter gains separated by sale date):")
    X["stcg_eq_pre"]  = max(0.0, float(st.number_input("STCG on listed equity/Equity MF (sale **before 23-Jul-2024**) (₹)", value=float(X["stcg_eq_pre"]), step=1000.0)))
    X["stcg_eq_post"] = max(0.0, float(st.number_input("STCG on listed equity/Equity MF (sale **on/after 23-Jul-2024**) (₹)", value=float(X["stcg_eq_post"]), step=1000.0)))
    X["ltcg_eq_pre"]  = max(0.0, float(st.number_input("LTCG on listed equity/Equity MF (sale **before 23-Jul-2024**) (₹)", value=float(X["ltcg_eq_pre"]), step=1000.0)))
    X["ltcg_eq_post"] = max(0.0, float(st.number_input("LTCG on listed equity/Equity MF (sale **on/after 23-Jul-2024**) (₹)", value=float(X["ltcg_eq_post"]), step=1000.0)))

    st.markdown("**Other capital gains:**")
    X["stcg_other_slab"] = max(0.0, float(st.number_input("Other STCG taxed at **slab** (₹)", value=float(X["stcg_other_slab"]), step=1000.0)))
    X["ltcg_20"] = max(0.0, float(st.number_input("Other LTCG **@20%** (₹)", value=float(X["ltcg_20"]), step=1000.0)))
    X["ltcg_10"] = max(0.0, float(st.number_input("Other LTCG **@10%** (₹)", value=float(X["ltcg_10"]), step=1000.0)))

    # Compute preview taxes for display
    tax_stcg_eq_pre = 0.15 * X["stcg_eq_pre"]
    tax_stcg_eq_post = 0.20 * X["stcg_eq_post"]
    total_ltcg_eq = X["ltcg_eq_pre"] + X["ltcg_eq_post"]
    exemption = min(125000.0, total_ltcg_eq)
    post_taxable = max(0.0, X["ltcg_eq_post"] - exemption)
    rem = max(0.0, exemption - X["ltcg_eq_post"])
    pre_taxable = max(0.0, X["ltcg_eq_pre"] - rem)
    tax_ltcg_eq = 0.125 * post_taxable + 0.10 * pre_taxable

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tax STCG Eq (pre 23 Jul) @15%", inr(tax_stcg_eq_pre))
    col2.metric("Tax STCG Eq (post 23 Jul) @20%", inr(tax_stcg_eq_post))
    col3.metric("Eq LTCG exemption applied", inr(exemption))
    col4.metric("Tax LTCG Eq (mix)", inr(tax_ltcg_eq))

# ---------- Step 5: Other Income & Deductions ----------
if step.startswith("5"):
    st.header("5) Other Income & Deductions")
    X["other_slab_income"] = max(0.0, float(st.number_input("Any OTHER slab-taxed income (e.g., salary/consulting in India) (₹)", value=float(X["other_slab_income"]), step=1000.0)))
    X["other_deductions"] = max(0.0, float(st.number_input("Total other deductions (80C/80D/80G etc.) **EXCLUDING 80TTA** (₹)", value=float(X["other_deductions"]), step=1000.0)))

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
    tax_stcg_eq_pre = 0.15 * X["stcg_eq_pre"]
    tax_stcg_eq_post = 0.20 * X["stcg_eq_post"]
    total_ltcg_eq = X["ltcg_eq_pre"] + X["ltcg_eq_post"]
    exemption = min(125000.0, total_ltcg_eq)
    post_taxable = max(0.0, X["ltcg_eq_post"] - exemption)
    rem = max(0.0, exemption - X["ltcg_eq_post"])
    pre_taxable = max(0.0, X["ltcg_eq_pre"] - rem)
    tax_ltcg_eq = 0.125 * post_taxable + 0.10 * pre_taxable

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
    tax_111A = tax_stcg_eq_pre + tax_stcg_eq_post
    tax_112A = tax_ltcg_eq
    tax_112 = tax_ltcg_20 + tax_ltcg_10

    # Total income for surcharge purposes (approximate; non-negative sums)
    total_income = 0.0
    total_income += max(0.0, income_hp)
    total_income += taxable_interest
    total_income += X["stcg_other_slab"]
    total_income += X["stcg_eq_pre"] + X["stcg_eq_post"]
    total_income += total_ltcg_eq
    total_income += X["ltcg_20"] + X["ltcg_10"]
    total_income += X["other_slab_income"]
    total_income = max(0.0, total_income - X["other_deductions"])

    surcharge, surcharge_break = apply_surcharge_with_caps(tax_on_slab, tax_111A, tax_112A, tax_112, total_income)
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
            "stcg_eq_pre": X["stcg_eq_pre"],
            "stcg_eq_post": X["stcg_eq_post"],
            "ltcg_eq_pre": X["ltcg_eq_pre"],
            "ltcg_eq_post": X["ltcg_eq_post"],
            "ltcg_eq_total": total_ltcg_eq,
            "ltcg_eq_exemption_applied": exemption,
            "ltcg_eq_post_taxable": post_taxable,
            "ltcg_eq_pre_taxable": pre_taxable,
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
        "net_payable_positive_else_refund_negative": net_payable
    }

# ---------- Step 7: Summary ----------
if step.startswith("7"):
    st.header("7) Summary, Table & Excel Download")
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
    st.markdown("#### Detailed JSON (full)")
    st.json(summary)

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
    st.download_button(
        "⬇️ Download Excel (FY 2024-25)",
        data=data,
        file_name="nri_itr_summary_fy2024_25.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.sidebar.markdown("---")
st.sidebar.caption("This tool assumes **Old Regime**, applies 80TTA on NRO savings, equity CG changes from **23-Jul-2024**, and surcharge caps on special-rate gains. Health & Education Cess at 4%.")
st.sidebar.caption("Always cross-check with your Form 26AS/AIS & ITR utility. For edge cases, consult a CA.")
