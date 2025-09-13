# NRI ITR Wizard — FY 2024-25 (AY 2025-26)

A Streamlit app for **NRIs (Middle East)** to estimate Indian income tax under the **Old Regime** for **FY 2024-25**. Covers:
- **House Property (rent)** — NAV, 30% standard deduction, set-off of HP loss capped at ₹2,00,000
- **Interest** — 80TTA on **NRO savings** (up to ₹10,000); NRE/FCNR treated **exempt** in India
- **Capital Gains** — Listed equity rate changes from **23-Jul-2024** handled by sale-date inputs:
  - STCG (111A): 15% (pre 23-Jul-2024), 20% (on/after 23-Jul-2024)
  - LTCG (112A): exemption ₹1,25,000; 10% (pre 23-Jul-2024) / 12.5% (on/after 23-Jul-2024)
- **Surcharge** bands, **cap 15%** on 111A/112/112A taxes, and **4% cess**
- **Credits** — TDS/TCS and Advance/SAT
- **Summary table** on screen + **Excel** download (multiple sheets)

> **Disclaimer:** Educational estimator only; not a filing utility. Cross-check with the Income Tax e-Filing portal, AIS/26AS, and consult a CA for complex cases (marginal relief, DTAA, multiple properties, etc.).

## Quickstart (local)

```bash
python -m venv .venv
# Windows
. .venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
python -m streamlit run streamlit_app.py
