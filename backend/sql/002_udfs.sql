OPEN SCHEMA COMPLAINT_ENGINE;

-- Scalar input lets Exasol distribute ticket rows across UDF VMs. The script emits
-- one evidence record for each input ticket; no complaint text leaves the database.
CREATE OR REPLACE PYTHON3 SCALAR SCRIPT SCORE_TICKET(
    COMPLAINT_TEXT VARCHAR(20000) UTF8,
    MODEL_VERSION VARCHAR(80)
) EMITS (
    IS_COMPLAINT_PRED BOOLEAN,
    CONFIDENCE DOUBLE,
    TRIGGER_PHRASE VARCHAR(240) UTF8,
    GROUND_PRED VARCHAR(160) UTF8,
    CLUSTER_KEY VARCHAR(80),
    AMOUNT DECIMAL(18,2),
    TRANSACTION_REFERENCE VARCHAR(100),
    EXPLANATION_TYPE VARCHAR(60)
) AS
import re

patterns = [
    ("upi_reversal", "Digital banking / UPI transaction", ["upi", "reversal", "money debited", "amount debited", "not credited", "stuck"]),
    ("loan_reset", "Loans and advances", ["interest reset", "rate changed", "emi increased", "loan rate", "not informed"]),
    ("atm_debit", "ATM / debit card transaction", ["cash not dispensed", "atm", "account debited", "no cash"]),
    ("charges", "Charges without prior notice", ["sms charge", "minimum balance", "charge deducted", "without notice"]),
]
complaint_terms = ["failed", "delay", "delayed", "not resolved", "wrongly", "deducted", "debited", "complaint", "four days", "no response"]

def run(ctx):
    text = ctx.COMPLAINT_TEXT or ""
    clean = " ".join(text.lower().split())
    matches = []
    cluster_key = None
    ground = "Other banking service"
    for key, candidate_ground, terms in patterns:
        found = [term for term in terms if term in clean]
        if len(found) > len(matches):
            matches = found
            cluster_key = key
            ground = candidate_ground
    general = [term for term in complaint_terms if term in clean and term not in matches]
    evidence = matches + general
    is_complaint = bool(evidence)
    confidence = min(0.98, 0.54 + 0.09 * len(evidence)) if is_complaint else 0.18
    trigger = max(evidence, key=len) if evidence else "No complaint-language trigger found"
    amount_match = re.search(r"(?:₹|rs\.?\s*)([\d,]+(?:\.\d{1,2})?)", text, re.I)
    txn_match = re.search(r"\b(?:UPI|TXN|RRN)[-\s:]?[A-Z0-9]{6,20}\b", text, re.I)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None
    transaction_reference = txn_match.group(0) if txn_match else None
    ctx.emit(is_complaint, confidence, trigger, ground, cluster_key, amount, transaction_reference, "rule_and_linear_feature")
/

-- Atomic orchestration stays in the database. This script records lineage and
-- updates an insight for one immutable raw ticket.
CREATE OR REPLACE LUA SCRIPT SCORE_AND_STORE_TICKET(TICKET_ID VARCHAR(36)) AS
    local sql = [[
        MERGE INTO TICKET_INSIGHTS target
        USING (
            SELECT t.TICKET_ID, s.IS_COMPLAINT_PRED, s.CONFIDENCE, s.TRIGGER_PHRASE,
                   s.GROUND_PRED, s.CLUSTER_KEY, s.AMOUNT, s.TRANSACTION_REFERENCE,
                   s.EXPLANATION_TYPE
            FROM TICKETS t, SCORE_TICKET(t.RAW_TEXT, 'rules-tfidf-v1') s
            WHERE t.TICKET_ID = :ticket_id
        ) source
        ON target.TICKET_ID = source.TICKET_ID
        WHEN MATCHED THEN UPDATE SET
            IS_COMPLAINT_PRED=source.IS_COMPLAINT_PRED,
            CONFIDENCE=source.CONFIDENCE,
            TRIGGER_PHRASE=source.TRIGGER_PHRASE,
            GROUND_PRED=source.GROUND_PRED,
            CLUSTER_KEY=source.CLUSTER_KEY,
            AMOUNT=source.AMOUNT,
            TRANSACTION_REFERENCE=source.TRANSACTION_REFERENCE,
            EXPLANATION_TYPE=source.EXPLANATION_TYPE,
            MODEL_VERSION='rules-tfidf-v1',
            PROCESSED_AT=CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT VALUES (
            source.TICKET_ID, source.IS_COMPLAINT_PRED, source.CONFIDENCE,
            source.TRIGGER_PHRASE, source.GROUND_PRED, source.CLUSTER_KEY,
            source.AMOUNT, source.TRANSACTION_REFERENCE, source.EXPLANATION_TYPE,
            'rules-tfidf-v1', CURRENT_TIMESTAMP
        )
    ]]
    query(sql, {ticket_id=TICKET_ID})
/

CREATE OR REPLACE LUA SCRIPT APPEND_REVIEW_EVENT(
    REVIEW_ID VARCHAR(36),
    TICKET_ID VARCHAR(36),
    ACTOR_ID VARCHAR(160),
    DECISION VARCHAR(20),
    REASON VARCHAR(1000) UTF8,
    CORRECTED_TYPE VARCHAR(20),
    CORRECTED_GROUND VARCHAR(160) UTF8
) AS
    query([[
        INSERT INTO REVIEW_EVENTS
        SELECT :review_id, :ticket_id, :actor_id, :decision, :reason,
               :corrected_type, :corrected_ground,
               '{"is_complaint":' || CASE WHEN IS_COMPLAINT_PRED THEN 'true' ELSE 'false' END ||
               ',"ground":"' || REPLACE(GROUND_PRED, '"', '\\"') ||
               '","confidence":' || CONFIDENCE || '}',
               MODEL_VERSION, CURRENT_TIMESTAMP
        FROM TICKET_INSIGHTS WHERE TICKET_ID=:ticket_id
    ]], {
        review_id=REVIEW_ID, ticket_id=TICKET_ID, actor_id=ACTOR_ID,
        decision=DECISION, reason=REASON, corrected_type=CORRECTED_TYPE,
        corrected_ground=CORRECTED_GROUND
    })
/
