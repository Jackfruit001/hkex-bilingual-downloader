"""Content check (SPEC §4.5): figures in an English PDF against a Chinese one."""

import multiprocessing
import multiprocessing.connection as mpc
import time
from collections import Counter

import pytest

from app.config import PAIRING, PairingConfig
from app.domain.models import Lang
from app.pairing.content_check import (
    ExtractedText,
    TextStatus,
    best_match,
    chinese_share,
    containment,
    extract_text,
    fingerprint,
    readable,
)
from tests.support import make_pdf

# --- fingerprint ----------------------------------------------------------------------------


def test_numbers_have_commas_removed_and_single_digits_dropped() -> None:
    assert fingerprint("Revenue 1,234,567 up 12.5% from 8 and 9") == Counter(
        {"1234567": 1, "12.5%": 1}
    )


def test_full_width_digits_are_folded() -> None:
    assert fingerprint("２０２６年１０月２８日") == Counter({"2026": 1, "10": 1, "28": 1})


def test_an_english_date_compares_with_a_chinese_date() -> None:
    assert fingerprint("28 October 2026") == fingerprint("2026年10月28日")


def test_repeated_figures_are_counted() -> None:
    assert fingerprint("HK$500 and HK$500 and 700")["500"] == 2


def test_no_numbers_gives_an_empty_fingerprint() -> None:
    assert fingerprint("Notice of annual general meeting") == Counter()


# --- containment and the verdict -------------------------------------------------------------


def test_containment_is_the_shared_share_of_the_smaller_side() -> None:
    en = Counter({"100": 1, "200": 1, "300": 1, "400": 1})
    tc = Counter({"100": 1, "200": 1, "999": 1})
    assert containment(en, tc) == pytest.approx(2 / 3)


def test_containment_counts_repeats_as_a_multiset() -> None:
    assert containment(Counter({"500": 2}), Counter({"500": 1})) == 1.0
    # the smaller side has 3 figures; 2 of them are shared
    assert containment(Counter({"500": 3}), Counter({"500": 2, "7": 4})) == pytest.approx(2 / 3)


def test_containment_of_an_empty_side_is_zero() -> None:
    assert containment(Counter(), Counter({"100": 1})) == 0.0


FIGURES = Counter({"2026": 1, "10": 1, "28": 1, "1500": 1, "250.5": 1, "88": 1})


def test_a_clear_best_match_is_conclusive() -> None:
    v = best_match("e1", FIGURES, {"t1": FIGURES, "t2": Counter({"31": 1, "700": 1})})
    assert v is not None
    assert (v.tc_news_id, v.conclusive, v.score) == ("t1", True, 1.0)
    assert v.runner_up == 0.0 and v.tokens == 6


def test_a_close_runner_up_is_not_conclusive() -> None:
    near = Counter({"2026": 1, "10": 1, "28": 1, "1500": 1, "250.5": 1, "77": 1})
    v = best_match("e1", FIGURES, {"t1": FIGURES, "t2": near})
    assert v is not None and v.tc_news_id == "t1" and not v.conclusive


def test_a_best_score_below_the_threshold_is_not_conclusive() -> None:
    weak = Counter({"2026": 1, "10": 1, "999": 1, "998": 1, "997": 1, "996": 1})
    v = best_match("e1", FIGURES, {"t1": weak})
    assert v is not None and v.score < 0.6 and not v.conclusive


def test_too_few_figures_are_not_conclusive() -> None:
    few = Counter({"2026": 1, "1500": 1})
    v = best_match("e1", few, {"t1": few})
    assert v is not None and v.score == 1.0 and not v.conclusive


def test_thresholds_come_from_the_config() -> None:
    cfg = PairingConfig(content_min_tokens=2)
    few = Counter({"2026": 1, "1500": 1})
    v = best_match("e1", few, {"t1": few}, cfg)
    assert v is not None and v.conclusive


def test_no_candidates_gives_no_verdict() -> None:
    assert best_match("e1", FIGURES, {}) is None


# --- text extraction (real pypdf, synthetic PDFs) ---------------------------------------------


LONG = [
    "Next Day Disclosure Return " + "x" * 80,
    "Number of shares 1,234,567 on 28 October 2026",
] * 2


def test_text_is_extracted_from_the_first_pages() -> None:
    result = extract_text(make_pdf([LONG]))
    assert result.status is TextStatus.OK
    assert "1,234,567" in result.text and "28 October 2026" in result.text


def test_only_the_first_pages_are_read() -> None:
    pdf = make_pdf([LONG, LONG, LONG, [*LONG, "SECRET-LAST-PAGE 424242"]])
    result = extract_text(pdf, pages=3)
    assert result.status is TextStatus.OK and "424242" not in result.text


def test_a_document_with_almost_no_text_is_reported_as_unavailable() -> None:
    result = extract_text(make_pdf([["scanned"]]))
    assert result.status is TextStatus.UNAVAILABLE


def test_bytes_that_are_not_a_pdf_are_an_error_not_a_crash() -> None:
    result = extract_text(b"<html>Access denied</html>")
    assert result.status is TextStatus.ERROR


def hang(conn: mpc.Connection, pdf: bytes, pages: int) -> None:
    time.sleep(60)


def test_a_hung_extraction_is_stopped_at_the_time_limit() -> None:
    started = time.monotonic()
    result = extract_text(make_pdf([LONG]), timeout_s=0.5, target=hang)
    assert result.status is TextStatus.TIMEOUT
    assert time.monotonic() - started < 10
    assert not multiprocessing.active_children()  # the hung worker was killed, not left running


def crash(conn: mpc.Connection, pdf: bytes, pages: int) -> None:
    raise SystemExit(3)


def test_a_worker_that_dies_without_answering_is_an_error() -> None:
    assert extract_text(make_pdf([LONG]), target=crash).status is TextStatus.ERROR


# --- Chinese text that cannot be decoded ------------------------------------------------------
# 21 of 62 real Chinese PDFs (31 October 2026) gave at most 2.8% Chinese characters: an embedded
# font pypdf cannot decode, so the "text" is gibberish with a few stray digits, yet it is longer
# than 200 characters and would pass for readable. The other 41 gave at least 14.5%.


def ok(text: str) -> ExtractedText:
    return ExtractedText(TextStatus.OK, text)


def test_the_chinese_share_ignores_whitespace_and_counts_only_chinese_characters() -> None:
    assert chinese_share("") == 0.0
    assert chinese_share("測試 公告 2026") == pytest.approx(4 / 8)
    assert chinese_share("Next Day Disclosure Return 28 October 2026") == 0.0


def test_readable_chinese_text_is_left_alone() -> None:
    extracted = ok("翌日披露報表 " * 20)
    assert readable(Lang.TC, extracted) is extracted


def test_chinese_text_with_almost_no_chinese_in_it_is_unavailable_and_says_why() -> None:
    gibberish = "Wֻ∉܋∉ ၵರ஼੝Ḹі ٺܢứྛದˢˢၘ 305 2026 " * 20
    result = readable(Lang.TC, ok(gibberish))
    assert result.status is TextStatus.UNAVAILABLE
    assert "Chinese" in result.detail and "%" in result.detail


def test_the_threshold_sits_inside_the_measured_gap() -> None:
    assert 0.028 < PAIRING.content_min_chinese_share < 0.145


def test_the_threshold_comes_from_the_config() -> None:
    text = ok("測試" + "x" * 8)  # 20% Chinese
    assert readable(Lang.TC, text, PairingConfig(content_min_chinese_share=0.5)).status is (
        TextStatus.UNAVAILABLE
    )
    assert readable(Lang.TC, text, PairingConfig(content_min_chinese_share=0.1)) is text


def test_english_text_is_never_held_to_the_chinese_rule() -> None:
    extracted = ok("Next Day Disclosure Return " * 20)
    assert readable(Lang.EN, extracted) is extracted


@pytest.mark.parametrize("status", [TextStatus.UNAVAILABLE, TextStatus.TIMEOUT, TextStatus.ERROR])
def test_a_status_that_is_already_bad_is_passed_through(status: TextStatus) -> None:
    extracted = ExtractedText(status, "x", "why")
    assert readable(Lang.TC, extracted) is extracted
