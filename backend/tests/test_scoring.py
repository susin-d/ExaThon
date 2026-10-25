from app.scoring import redact_excerpt, score_text


def test_complaint_language_is_detected_with_evidence():
    result = score_text("UPI TXN-ABC123 amount debited Rs. 4,850 four days ago and not credited")
    assert result.is_complaint is True
    assert result.confidence >= 0.8
    assert result.cluster_key == "upi_reversal"
    assert result.amount == 4850
    assert result.trigger_phrase in {"amount debited", "not credited", "four days", "upi"}


def test_genuine_query_remains_a_query():
    result = score_text("Please share branch timings and cheque book requirements")
    assert result.is_complaint is False
    assert result.cluster_key is None
    assert result.confidence < 0.5


def test_excerpt_redacts_long_numbers_and_email():
    excerpt = redact_excerpt("Account 1234567890123456 belongs to person@example.com")
    assert "1234567890123456" not in excerpt
    assert "person@example.com" not in excerpt
