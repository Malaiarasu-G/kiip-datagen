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

    # --- question_bank.xlsx: Fill rate (Q1-Q6) -----------------------------------
    SampleQuestion(
        id="historical_fill_rate_by_month",
        question="What is the fill rate for all historical orders, by month?",
        sql="""
            SELECT DATE_TRUNC('month', FST_PLAN_GI_DT) AS month,
                   ROUND(100.0 * SUM(DELV_QTY) / NULLIF(SUM(ORDR_QTY), 0), 1) AS unit_fill_rate_pct
            FROM historical
            WHERE CANCELLED_FL = 'NO' AND ORDR_TYPE_DESC = 'Standard'
            GROUP BY 1
            ORDER BY 1
        """,
    ),
    SampleQuestion(
        id="historical_fill_rate_by_dc_last_month",
        question="What was unit fill rate by DC last month?",
        sql="""
            SELECT PLNT_CD, PLNT_NM,
                   ROUND(100.0 * SUM(DELV_QTY) / NULLIF(SUM(ORDR_QTY), 0), 1) AS unit_fill_rate_pct
            FROM historical
            WHERE CANCELLED_FL = 'NO' AND ORDR_TYPE_DESC = 'Standard'
              AND FST_PLAN_GI_DT >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
              AND FST_PLAN_GI_DT <  DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY PLNT_CD, PLNT_NM
            ORDER BY unit_fill_rate_pct ASC
        """,
    ),
    SampleQuestion(
        id="historical_dollar_fill_rate_by_banner_last_quarter",
        question="What was dollar fill rate by customer banner last quarter?",
        sql="""
            SELECT KEY_CUST_NM,
                   ROUND(100.0 * SUM(DELV_VAL) / NULLIF(SUM(ORDR_VAL), 0), 1) AS dollar_fill_rate_pct
            FROM historical
            WHERE CANCELLED_FL = 'NO' AND ORDR_TYPE_DESC = 'Standard'
              AND FST_PLAN_GI_DT >= CURRENT_DATE - INTERVAL 3 MONTH
            GROUP BY KEY_CUST_NM
            ORDER BY dollar_fill_rate_pct ASC
        """,
    ),
    SampleQuestion(
        id="lowest_fill_rate_skus_last_month",
        question="Which 10 SKUs had the lowest fill rate last month?",
        sql="""
            SELECT MATERIAL, MATL_DESC,
                   ROUND(100.0 * SUM(DELV_QTY) / NULLIF(SUM(ORDR_QTY), 0), 1) AS unit_fill_rate_pct
            FROM historical
            WHERE CANCELLED_FL = 'NO' AND ORDR_TYPE_DESC = 'Standard'
              AND FST_PLAN_GI_DT >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
              AND FST_PLAN_GI_DT <  DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY MATERIAL, MATL_DESC
            HAVING SUM(ORDR_QTY) > 0
            ORDER BY unit_fill_rate_pct ASC
            LIMIT 10
        """,
    ),
    SampleQuestion(
        id="dc2_fill_rate_drop_investigation",
        question="Why did fill rate drop at DC2 last month? (planted pattern)",
        sql="""
            SELECT PLNT_CD, PLNT_NM, DATE_TRUNC('month', FST_PLAN_GI_DT) AS month, CUT_RSN_PRIM_DESC,
                   COUNT(*) AS lines, SUM(CUT_QTY) AS total_cut_qty,
                   ROUND(100.0 * SUM(DELV_QTY) / NULLIF(SUM(ORDR_QTY), 0), 1) AS unit_fill_rate_pct
            FROM historical
            WHERE CANCELLED_FL = 'NO' AND ORDR_TYPE_DESC = 'Standard'
            GROUP BY PLNT_CD, PLNT_NM, month, CUT_RSN_PRIM_DESC
            HAVING COUNT(*) >= 5
            ORDER BY unit_fill_rate_pct ASC
            LIMIT 20
        """,
    ),

    # --- Cuts, rejections and cancellations (Q7-Q11) -----------------------------
    SampleQuestion(
        id="cuts_by_reason_last_month",
        question="What were total cut cases last month, by primary cut reason?",
        sql="""
            SELECT CUT_RSN_PRIM_DESC, SUM(CUT_QTY) AS total_cut_cases, COUNT(*) AS lines
            FROM historical
            WHERE CUT_QTY > 0
              AND FST_PLAN_GI_DT >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
              AND FST_PLAN_GI_DT <  DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY CUT_RSN_PRIM_DESC
            ORDER BY total_cut_cases DESC
        """,
    ),
    SampleQuestion(
        id="cut_share_from_allocation_last_quarter",
        question="What share of cuts last quarter was due to allocation?",
        sql="""
            SELECT ROUND(100.0 * SUM(CASE WHEN CUT_RSN_PRIM_DESC = 'Allocation' THEN CUT_QTY ELSE 0 END)
                         / NULLIF(SUM(CUT_QTY), 0), 1) AS pct_cuts_from_allocation
            FROM historical
            WHERE CUT_QTY > 0 AND FST_PLAN_GI_DT >= CURRENT_DATE - INTERVAL 3 MONTH
        """,
    ),
    SampleQuestion(
        id="cut_trace_recent",
        question="Why were orders for a given SKU cut last week? (traced to allocation where applicable)",
        sql="""
            SELECT h.MATERIAL, h.MATL_DESC, h.PLNT_CD, h.FST_PLAN_GI_DT, h.ORDR_QTY, h.CUT_QTY,
                   h.CUT_RSN_PRIM_DESC, a.ALLOC_STATUS, a.PARENT_CODE
            FROM historical h
            LEFT JOIN dim_product p ON p.material = h.MATERIAL
            LEFT JOIN allocation a
                   ON a.PARENT_CODE = p.material_parent_cd
                  AND a.CALENDAR_DT = h.FST_PLAN_GI_DT
            WHERE h.CUT_QTY > 0
              AND h.FST_PLAN_GI_DT >= CURRENT_DATE - INTERVAL 7 DAY
            ORDER BY h.FST_PLAN_GI_DT DESC
            LIMIT 20
        """,
    ),
    SampleQuestion(
        id="rejection_rate_by_customer_last_quarter",
        question="Which customers had the highest rejection rate last quarter, and what were the secondary reasons?",
        sql="""
            SELECT KEY_CUST_NM,
                   COUNT(*) AS total_lines,
                   SUM(CASE WHEN RJCTN_RSN_PRIM_CD IS NOT NULL THEN 1 ELSE 0 END) AS rejected_lines,
                   ROUND(100.0 * SUM(CASE WHEN RJCTN_RSN_PRIM_CD IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS rejection_rate_pct,
                   MODE(RJCTN_RSN_SECO_DESC) AS most_common_secondary_reason
            FROM historical
            WHERE FST_PLAN_GI_DT >= CURRENT_DATE - INTERVAL 3 MONTH
            GROUP BY KEY_CUST_NM
            ORDER BY rejection_rate_pct DESC
        """,
    ),
    SampleQuestion(
        id="cancellation_rate_by_reason_this_year",
        question="What is the cancellation rate by reason code this year?",
        sql="""
            SELECT CANCELLED_RSN_DESC,
                   COUNT(*) AS cancelled_lines,
                   ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM historical
                                              WHERE DATE_PART('year', FST_PLAN_GI_DT) = DATE_PART('year', CURRENT_DATE)), 2) AS pct_of_all_lines
            FROM historical
            WHERE CANCELLED_FL = 'YES' AND DATE_PART('year', FST_PLAN_GI_DT) = DATE_PART('year', CURRENT_DATE)
            GROUP BY CANCELLED_RSN_DESC
            ORDER BY cancelled_lines DESC
        """,
    ),

    # --- On-time (Q12-Q15) --------------------------------------------------------
    SampleQuestion(
        id="on_time_rate_last_month",
        question="What share of order lines shipped on or before the requested date last month?",
        sql="""
            SELECT ROUND(100.0 * SUM(CASE WHEN FST_ACTL_SHIP_DT <= CUST_REQ_DELV_DT THEN 1 ELSE 0 END)
                         / NULLIF(SUM(CASE WHEN FST_ACTL_SHIP_DT IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS on_time_rate_pct
            FROM historical
            WHERE FST_PLAN_GI_DT >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
              AND FST_PLAN_GI_DT <  DATE_TRUNC('month', CURRENT_DATE)
        """,
    ),
    SampleQuestion(
        id="on_time_month_over_month",
        question="How does on-time performance this month compare with last month?",
        sql="""
            SELECT DATE_TRUNC('month', FST_PLAN_GI_DT) AS month,
                   ROUND(100.0 * SUM(CASE WHEN FST_ACTL_SHIP_DT <= CUST_REQ_DELV_DT THEN 1 ELSE 0 END)
                         / NULLIF(SUM(CASE WHEN FST_ACTL_SHIP_DT IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS on_time_rate_pct
            FROM historical
            WHERE FST_PLAN_GI_DT >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
            GROUP BY 1
            ORDER BY 1
        """,
    ),
    SampleQuestion(
        id="worst_dc_on_time_this_quarter",
        question="Which DC had the worst on-time performance this quarter?",
        sql="""
            SELECT PLNT_CD, PLNT_NM,
                   ROUND(100.0 * SUM(CASE WHEN FST_ACTL_SHIP_DT <= CUST_REQ_DELV_DT THEN 1 ELSE 0 END)
                         / NULLIF(SUM(CASE WHEN FST_ACTL_SHIP_DT IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS on_time_rate_pct
            FROM historical
            WHERE FST_PLAN_GI_DT >= CURRENT_DATE - INTERVAL 3 MONTH
            GROUP BY PLNT_CD, PLNT_NM
            ORDER BY on_time_rate_pct ASC
        """,
    ),
    SampleQuestion(
        id="late_gi_investigation",
        question="Why did on-time performance fall in a recent week at a given DC? (planted pattern)",
        sql="""
            SELECT PLNT_CD, PLNT_NM, DATE_TRUNC('week', FST_PLAN_GI_DT) AS week,
                   COUNT(*) AS lines,
                   ROUND(100.0 * SUM(CASE WHEN FST_ACTL_SHIP_DT <= CUST_REQ_DELV_DT THEN 1 ELSE 0 END)
                         / NULLIF(SUM(CASE WHEN FST_ACTL_SHIP_DT IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS on_time_rate_pct
            FROM historical
            WHERE FST_PLAN_GI_DT >= CURRENT_DATE - INTERVAL 60 DAY
            GROUP BY PLNT_CD, PLNT_NM, week
            HAVING COUNT(*) >= 5
            ORDER BY on_time_rate_pct ASC
            LIMIT 20
        """,
    ),

    # --- Blocks (Q16-Q17) ----------------------------------------------------------
    SampleQuestion(
        id="block_rate_by_code",
        question="What is the current order block rate, by block code?",
        sql="""
            SELECT DELIVERY_BLOCK_CD, DELIVERY_BLOCK_DESC, COUNT(*) AS blocked_lines,
                   ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM shipments), 2) AS pct_of_open_book
            FROM shipments
            WHERE DELIVERY_BLOCK_CD IS NOT NULL
            GROUP BY DELIVERY_BLOCK_CD, DELIVERY_BLOCK_DESC
            ORDER BY blocked_lines DESC
        """,
    ),
    SampleQuestion(
        id="customers_most_blocked",
        question="Which customers have the most blocked orders, and what is the value on hold?",
        sql="""
            SELECT KEY_CUST_NM,
                   COUNT(*) AS blocked_lines,
                   ROUND(SUM(GTS_Order), 2) AS value_on_hold
            FROM shipments
            WHERE DELIVERY_BLOCK_CD IS NOT NULL OR BILLING_BLOCK_CD IS NOT NULL OR CREDIT_BLOCK_CD IS NOT NULL
            GROUP BY KEY_CUST_NM
            ORDER BY blocked_lines DESC
            LIMIT 15
        """,
    ),

    # --- Allocation, ATP and inbound (Q19-Q22) --------------------------------------
    SampleQuestion(
        id="allocation_consumption_by_group_this_month",
        question="What is allocation consumption by customer group this month?",
        sql="""
            SELECT CUSTOMER_GROUP,
                   ROUND(100.0 * SUM(ORDERED_QTY) / NULLIF(SUM(ALLOCATED_QTY), 0), 1) AS pct_consumed
            FROM allocation
            WHERE DATE_TRUNC('month', CALENDAR_DT) = DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY CUSTOMER_GROUP
            ORDER BY pct_consumed DESC
        """,
    ),
    SampleQuestion(
        id="customers_over_90pct_allocation",
        question="Which customers have consumed more than 90% of their allocation?",
        sql="""
            SELECT PARENT_CODE, PARENT_DESC, CUSTOMER_GROUP, CALENDAR_DT, PCT_CONSUMED
            FROM allocation
            WHERE PCT_CONSUMED > 90
            ORDER BY PCT_CONSUMED DESC
            LIMIT 20
        """,
    ),
    SampleQuestion(
        id="atp_by_dc_for_sku",
        question="What is ATP for a given SKU by DC, in cases and eaches?",
        sql="""
            SELECT a.material, p.material_desc, a.dc, a.atp_eaches, a.atp_cases
            FROM atp_snapshot a
            JOIN dim_product p ON p.material = a.material
            ORDER BY a.material, a.dc
            LIMIT 30
        """,
    ),
    SampleQuestion(
        id="inbound_qty_next_4_weeks",
        question="What inbound quantity is expected for a given SKU over the next 4 weeks?",
        sql="""
            SELECT material, dc, inbound_week, inbound_qty_cases
            FROM inbound_schedule
            WHERE inbound_week <= (SELECT MIN(inbound_week) FROM inbound_schedule) + INTERVAL 27 DAY
            ORDER BY material, dc, inbound_week
            LIMIT 40
        """,
    ),

    # --- V-report (Q24-Q26) ---------------------------------------------------------
    SampleQuestion(
        id="red_skus_next_two_weeks",
        question="How many SKUs are on red V-report in the next two weeks?",
        sql="""
            SELECT COUNT(DISTINCT MATERIAL) AS red_sku_count
            FROM vulnerability
            WHERE HORIZON_OFFSET BETWEEN 1 AND 2
              AND STATUS IN ('Red', 'Red-Black')
        """,
    ),
    SampleQuestion(
        id="vreport_status_distribution_this_week",
        question="What is the V-report status distribution this week?",
        sql="""
            SELECT STATUS, COUNT(*) AS sku_count
            FROM vulnerability
            WHERE HORIZON_OFFSET = 0 AND WEEK_START_DATE = (
                SELECT MAX(WEEK_START_DATE) FROM vulnerability WHERE HORIZON_OFFSET = 0
            )
            GROUP BY STATUS
            ORDER BY sku_count DESC
        """,
    ),
    SampleQuestion(
        id="yellow_to_red_movers",
        question="Which SKUs moved from Yellow to Red since last week? (planted pattern)",
        sql="""
            WITH weeks AS (
                SELECT DISTINCT WEEK_START_DATE FROM vulnerability WHERE HORIZON_OFFSET = 0
                ORDER BY WEEK_START_DATE DESC LIMIT 2
            )
            SELECT cur.MATERIAL, cur.MATERIAL_DESC, prev.STATUS AS prior_status, cur.STATUS AS latest_status
            FROM vulnerability cur
            JOIN vulnerability prev
              ON prev.MATERIAL = cur.MATERIAL
             AND prev.HORIZON_OFFSET = 0
             AND prev.WEEK_START_DATE = (SELECT MIN(WEEK_START_DATE) FROM weeks)
            WHERE cur.HORIZON_OFFSET = 0
              AND cur.WEEK_START_DATE = (SELECT MAX(WEEK_START_DATE) FROM weeks)
              AND prev.STATUS = 'Yellow' AND cur.STATUS IN ('Red', 'Red-Black')
        """,
    ),
]
