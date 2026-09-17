"""Shared code/description/weight lookups for order-processing fields.

Centralized here — rather than duplicated per fact-table module — so the
generated reference docs (scripts/build_reference_docs.py) never drift from
what the generator actually draws from, and so tables that share a domain
(e.g. historical's and shipments' delivery-block codes) stay in sync.

Lists that include a `(None, None)` entry are sampled directly via a single
weighted `rng.choice` (the "not applicable" case is baked into the weights).
Lists without one are paired with a separate rate (see config.yaml
business_rules) that gates whether the field applies at all; the list then
only decides *which* code, given that it applies.
"""
from __future__ import annotations

import numpy as np


def gated_code_draw(rng: np.random.Generator, n: int, rate: float, codes, weights):
    """Rate-gated pick from a (code, desc) list with no built-in None entry —
    returns (code_array, desc_array), None where the gate didn't fire.

    Shared by every fact table that models "does this field apply at all"
    (a rate) separately from "which code, given that it applies" (a fixed
    weighted domain) — e.g. the three block-code columns and historical's
    rejection reasons.
    """
    applies = rng.random(n) < rate
    idx = rng.choice(len(codes), size=n, p=weights)
    code = np.where(applies, [codes[i][0] for i in idx], None)
    desc = np.where(applies, [codes[i][1] for i in idx], None)
    return code, desc


# --- rejection reasons (shipments.py; also historical.py's rejection rate gate) ---
REJECTION_CODES = [
    (None, None),
    ("ZA", "Rejected - Customer Request"),
    ("ZB", "Rejected - Credit Block"),
    ("ZC", "Rejected - Pricing Dispute"),
]
REJECTION_WEIGHTS = [0.85, 0.08, 0.04, 0.03]

# --- allocation reason codes (allocation.py) --------------------------------
KC_CODES = [
    (None, None),
    ("SS", "Short Supply"),
    ("NC", "New Capacity Ramp"),
    ("QH", "Quality Hold"),
]
KC_WEIGHTS = [0.5, 0.3, 0.2]

# --- cut reasons (historical.py) --------------------------------------------
# "Allocation" is deliberately one of these — historical.py biases toward it
# when the material's parent was realized on-allocation that week (see its
# allocation-linkage), so cut-reason questions trace back to a real cause.
CUT_REASON_CODES = [
    ("ALOC", "Allocation"),
    ("QLTY", "Quality Hold"),
    ("CAPY", "Capacity Constraint"),
    ("TRAN", "Transportation Delay"),
    ("OTHR", "Other"),
]
CUT_REASON_WEIGHTS = [0.35, 0.20, 0.20, 0.15, 0.10]

# --- cancellation reasons (historical.py) -----------------------------------
CANCELLATION_REASON_CODES = [
    ("CNCA", "Customer No Longer Needs"),
    ("CNCB", "Duplicate Order"),
    ("CNCC", "Price Discrepancy"),
    ("CNCD", "Found Alternate Supply"),
]
CANCELLATION_REASON_WEIGHTS = [0.4, 0.25, 0.2, 0.15]

# --- order types (historical.py) --------------------------------------------
# Non-Standard types exist so "exclude returns/free goods/samples" questions
# have something real to filter against.
ORDER_TYPE_CODES = [
    ("ZOR", "Standard"),
    ("ZRE", "Return"),
    ("ZFD", "Free Goods"),
    ("ZSA", "Sample"),
    ("ZIC", "Intercompany"),
]
ORDER_TYPE_WEIGHTS = [0.86, 0.05, 0.04, 0.03, 0.02]

# --- delivery/billing/credit block codes (shipments.py, historical.py) ------
# No (None, None) entry — each is paired with its own business_rules.*_block_rate
# gate; these lists only decide which code, given that a row is blocked.
DELIVERY_BLOCK_CODES = [
    ("01", "Delivery Block - Credit Hold"),
    ("02", "Delivery Block - Customer Request"),
]
DELIVERY_BLOCK_WEIGHTS = [0.6, 0.4]

BILLING_BLOCK_CODES = [
    ("B1", "Billing Block - Price Review"),
    ("B2", "Billing Block - Missing Documentation"),
]
BILLING_BLOCK_WEIGHTS = [0.5, 0.5]

CREDIT_BLOCK_CODES = [
    ("C1", "Credit Block - Over Limit"),
    ("C2", "Credit Block - Past Due"),
]
CREDIT_BLOCK_WEIGHTS = [0.5, 0.5]
