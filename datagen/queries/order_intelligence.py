"""Named SQL questions against the generated DuckDB.

This doubles as:
  - seed content for the "Q&A - Order Intelligence" unstructured source
  - a smoke test that the generated tables actually answer the kinds of
    questions the chatbot PoC needs to handle

Run scripts/run_sample_questions.py to execute all of these and render
docs/sample_qa_output.md. Add new questions here — never hand-edit that
generated file.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SampleQuestion:
    id: str
    question: str
    sql: str


QUESTIONS = [
    SampleQuestion(
        id="open_orders_for_customer",
        question="What open orders does a key customer have right now? (shown for one example customer)",
        sql="""
            SELECT Sales_Doc, Item, Material, MATL_SHRT_DESC, Order_Quantity, Confirmed_Qty, GI_Date
            FROM shipments
            WHERE KEY_CUST_NUM = (SELECT KEY_CUST_NUM FROM shipments LIMIT 1)
            ORDER BY GI_Date
            LIMIT 20
        """,
    ),
    SampleQuestion(
        id="fill_rate_by_customer",
        question="What is our unit fill rate by customer for the current open-order snapshot?",
        sql="""
            SELECT KEY_CUST_NM,
                   ROUND(100.0 * SUM(Confirmed_Qty) / NULLIF(SUM(Order_Quantity), 0), 1) AS unit_fill_rate_pct
            FROM shipments
            GROUP BY KEY_CUST_NM
            ORDER BY unit_fill_rate_pct ASC
        """,
    ),
    SampleQuestion(
        id="why_orders_short",
        question="Which order lines shipped short, and why?",
        sql="""
            SELECT Sales_Doc, Item, MATL_SHRT_DESC, Order_Quantity, Confirmed_Qty, Rj, Rejection_Description
            FROM shipments
            WHERE Confirmed_Qty < Order_Quantity
            LIMIT 10
        """,
    ),
    SampleQuestion(
        id="skus_on_allocation_today",
        question="Which SKUs are on allocation right now, and why?",
        sql="""
            SELECT PARENT_CODE, PARENT_DESC, SC_BRAND, KC_DESC, CALENDAR_DT, PERIOD
            FROM allocation
            WHERE ALLOC_STATUS = 'On Allocation'
              AND CALENDAR_DT = (SELECT MAX(CALENDAR_DT) FROM allocation)
            ORDER BY PARENT_CODE
            LIMIT 20
        """,
    ),
    SampleQuestion(
        id="highest_vulnerability_skus",
        question="Which materials are the most supply-vulnerable this week, and why?",
        sql="""
            SELECT MATERIAL, MATERIAL_DESC, RISK_TIER, BACKORDER_RISK_SCORE, SINGLE_SOURCE_FLAG, DAYS_OF_SUPPLY
            FROM vulnerability
            WHERE WEEK_START_DATE = (SELECT MAX(WEEK_START_DATE) FROM vulnerability)
            ORDER BY BACKORDER_RISK_SCORE DESC
            LIMIT 15
        """,
    ),
    SampleQuestion(
        id="etd_by_lane",
        question=(
            "By customer segment and plant, how many days after the planned "
            "goods-issue date do orders actually ship, and how often are they "
            "late? (this is our ETD signal)"
        ),
        sql="""
            SELECT CUST_SEG_CD, PLNT_CD,
                   COUNT(*) AS order_lines,
                   ROUND(AVG(DATE_DIFF('day', FST_PLAN_GI_DT, FST_ACTL_SHIP_DT)), 1) AS avg_days_actual_vs_planned,
                   ROUND(100.0 * SUM(CASE WHEN LATE_FL_MAD_IND = 'YES' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_late
            FROM historical
            WHERE FST_ACTL_SHIP_DT IS NOT NULL
            GROUP BY CUST_SEG_CD, PLNT_CD
            ORDER BY pct_late DESC
        """,
    ),
    SampleQuestion(
        id="otif_style_filter",
        question=(
            "OTIF isn't a stored metric — compute an OTIF-style on-time-in-full "
            "rate for the current open-order snapshot."
        ),
        sql="""
            SELECT
                ROUND(100.0 * SUM(CASE WHEN GI_Date <= Req_dlv_dt AND Confirmed_Qty >= Order_Quantity THEN 1 ELSE 0 END)
                      / COUNT(*), 1) AS otif_style_rate_pct
            FROM shipments
        """,
    ),
    SampleQuestion(
        id="cut_rate_by_brand",
        question="Which brands have the highest order-line cut rate? (a 'why are sales declining' diagnostic)",
        sql="""
            SELECT SC_BRND_DESC,
                   COUNT(*) AS total_lines,
                   SUM(CASE WHEN Confirmed_Qty < Order_Quantity THEN 1 ELSE 0 END) AS cut_lines,
                   ROUND(100.0 * SUM(CASE WHEN Confirmed_Qty < Order_Quantity THEN 1 ELSE 0 END) / COUNT(*), 1) AS cut_rate_pct
            FROM shipments
            GROUP BY SC_BRND_DESC
            ORDER BY cut_rate_pct DESC
        """,
    ),
    SampleQuestion(
        id="npi_lines_open",
        question="What new-product-introduction (NPI) lines are currently open?",
        sql="""
            SELECT Sales_Doc, Item, MATL_SHRT_DESC, KEY_CUST_NM, Order_Quantity, Confirmed_Qty
            FROM shipments
            WHERE NPI_Line_Flag = TRUE
            LIMIT 20
        """,
    ),
    SampleQuestion(
        id="discontinued_with_open_orders",
        question="Do we have open orders for materials that are obsolete or discontinued?",
        sql="""
            SELECT Sales_Doc, Item, MATL_SHRT_DESC, DSTN_CHN_STS_CD, Order_Quantity
            FROM shipments
            WHERE DSTN_CHN_STS_CD IN ('32', '33')
            LIMIT 20
        """,
    ),
]
