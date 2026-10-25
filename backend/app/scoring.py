import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Score:
    is_complaint: bool
    confidence: float
    trigger_phrase: str
    ground: str
    cluster_key: str | None
    amount: float | None
    transaction_reference: str | None
    explanation_type: str = "rule_and_linear_feature"
    model_version: str = "rules-tfidf-v1"
    processed_at: str = datetime.now(UTC).isoformat()


PATTERNS = [
    (
        "upi_reversal",
        "Digital banking / UPI transaction",
        ["upi", "reversal", "money debited", "amount debited", "not credited", "stuck"],
    ),
    (
        "loan_reset",
        "Loans and advances",
        ["interest reset", "rate changed", "emi increased", "loan rate", "not informed"],
    ),
    (
        "atm_debit",
        "ATM / debit card transaction",
        ["cash not dispensed", "atm", "account debited", "no cash"],
    ),
    (
        "charges",
        "Charges without prior notice",
        ["sms charge", "minimum balance", "charge deducted", "without notice"],
    ),
]
COMPLAINT_TERMS = [
    "failed",
    "delay",
    "delayed",
    "not resolved",
    "wrongly",
    "deducted",
    "debited",
    "complaint",
    "four days",
    "no response",
]


def score_text(text: str) -> Score:
    clean = " ".join(text.lower().split())
    matches: list[str] = []
    cluster_key = None
    ground = "Other banking service"
    for key, candidate_ground, terms in PATTERNS:
        found = [term for term in terms if term in clean]
        if len(found) > len(matches):
            matches = found
            cluster_key = key
            ground = candidate_ground

    general = [term for term in COMPLAINT_TERMS if term in clean]
    evidence = matches + [term for term in general if term not in matches]
    is_complaint = bool(evidence)
    confidence = min(0.98, 0.54 + 0.09 * len(evidence)) if is_complaint else 0.18
    trigger = max(evidence, key=len) if evidence else "No complaint-language trigger found"
    amount_match = re.search(
        r"(?:₹|rs\.?\s*)([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE
    )
    txn_match = re.search(
        r"\b(?:UPI|TXN|RRN)[-\s:]?[A-Z0-9]{6,20}\b", text, re.IGNORECASE
    )
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None
    reference = txn_match.group(0) if txn_match else None
    return Score(is_complaint, confidence, trigger, ground, cluster_key, amount, reference)


def redact_excerpt(text: str, limit: int = 260) -> str:
    text = re.sub(r"\b\d{10,16}\b", "••••REDACTED••••", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "•••@•••", text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
