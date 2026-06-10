"""
test_classifier.py — Manual test for the Facebook post classifier.

Run:
    python test_classifier.py

No external dependencies. Just checks that sample posts are classified correctly.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Import only the classifier functions (no Selenium / schedule needed)
from facebook_agent import classify_post, extract_price, extract_rooms, extract_location

# ─── Sample posts and expected classifications ────────────────────────────────

TESTS = [
    # (post_text, dedicated_group, expected_classification)

    # Should be RELEVANT
    (
        "דירת 3 חדרים להשכרה בשכונה ב, כניסה מיידית, 3500 ש\"ח לחודש, בעל דירה",
        True,
        "relevant_rental_apartment",
    ),
    (
        "דירה מתפנה ברחוב ביאליק, 2.5 חדרים, 3800₪ כולל ועד בית, מתאימה לזוג",
        True,
        "relevant_rental_apartment",
    ),
    (
        "יחידת דיור להשכרה, כניסה גמישה, שכ\"ד 3200",
        True,
        "relevant_rental_apartment",
    ),
    (
        "סטודיו להשכרה בבאר שבע, 2800 לחודש, כניסה מיידית",
        True,
        "relevant_rental_apartment",
    ),
    (
        "דירת 2 חדרים מתפנה, חוזה שנתי, 4000 ש\"ח",
        False,  # non-dedicated group
        "relevant_rental_apartment",
    ),

    # Short posts on dedicated groups — rental keyword alone scores 4+2=6 → relevant
    (
        "דירה להשכרה, פרטים בפרטי",
        True,
        "relevant_rental_apartment",
    ),
    (
        "להשכרה, 3 חדרים",
        True,
        "relevant_rental_apartment",
    ),
    # Non-dedicated group, "דירה להשכרה" alone = score 4 → still relevant (high recall)
    (
        "דירה להשכרה",
        False,
        "relevant_rental_apartment",
    ),
    # "דירה מתפנה" = rental_keyword(4) + availability(2) = 6 → relevant
    (
        "דירה מתפנה",
        False,
        "relevant_rental_apartment",
    ),
    # availability(2) + rooms(2) = score 4 → relevant (high recall is OK)
    (
        "פנוי מיידית, 3 חדרים",
        False,
        "relevant_rental_apartment",
    ),
    # Availability word alone, no apartment context → irrelevant
    # (prevents food/service ads that say "זמין"/"פנוי" from leaking)
    (
        "כניסה מיידית",
        False,
        "irrelevant",
    ),

    # ── Seeker posts that were incorrectly passing ─────────────────────────
    # "מחפשת דירת X להשכרה... אשמח להצעות" — seeker, not offer
    (
        "מחפשת דירת 4 חדרים להשכרה מחפשת דירת 4 חדרים ברגר אשמח להצעות",
        True,
        "seeker_post",
    ),
    # "אני ובן הזוג מחפשים דירת... נשמח לשמוע" — seeker
    (
        "היי אני ובן הזוג שלי מחפשים דירת 3 חדרים ללא תיווך כניסה ב-1.7 נשמח לשמוע",
        True,
        "seeker_post",
    ),
    # "מחפשת בית קרקע... לזוג... עד 3500" — seeker
    (
        "מחפשת בית קרקע דירת גן עם 4 חדרים לזוג עד 3500",
        True,
        "seeker_post",
    ),

    # ── Roommate posts that were incorrectly passing ───────────────────────
    # "אני מחפש את השותפים/ות הבאים" — roommate
    (
        "2 חדרים מתפנים בדירה אני מחפש את השותפים הבאים לדירה מאוד חשוב הסדר",
        True,
        "room_or_roommate_listing",
    ),
    # "מסבלטת את החדר... מחפשת מחליפה" — sublet/roommate
    (
        "בעקבות חילופי סטודנטים אני מסבלטת את החדר שלי ומחפשת מחליפה דירת 4 חדרים 3 שותפים",
        True,
        "room_or_roommate_listing",
    ),
    # "מתפנה חדר... דירת 3 שותפים... סאבלט" — roommate/sublet
    (
        "מתפנה חדר באביסרור דירת 3 שותפים כניסה מיידית לסאבלט 1735 שח",
        True,
        "room_or_roommate_listing",
    ),
    # "מחפשות שותפ/ה שיכנסו איתנו" — roommate
    (
        "מחפשות שותפה שיכנסו איתנו לדירת 4 חדרים ברגר 2 שותפות 1200 שכד",
        True,
        "room_or_roommate_listing",
    ),

    # ── Tricky: landlord says "בעל הדירה" + seeker word → should be RELEVANT ──
    (
        "בעל הדירה מחפש דיירים לדירת 3 חדרים להשכרה 3500 שח",
        True,
        "relevant_rental_apartment",
    ),

    # Should be OVER BUDGET
    (
        "דירת 3 חדרים להשכרה בשכונה ב, 5500₪ לחודש, כניסה ב-1/7",
        True,
        "over_budget",
    ),

    # Should be SEEKER POST
    (
        "מחפשת דירה לשכירות בשכונה ב, תקציב עד 4000, אשמח להצעות",
        True,
        "seeker_post",
    ),
    (
        "זוג מחפש דירה 2-3 חדרים בבאר שבע, אנא פנו אלינו",
        True,
        "seeker_post",
    ),
    (
        "סטודנט מחפש דירה קרוב לאוניברסיטה",
        True,
        "seeker_post",
    ),

    # Should be ROOMMATE listing
    (
        "חדר פנוי בדירת שותפים, 1600 לחודש, זמין מיד",
        True,
        "room_or_roommate_listing",
    ),
    (
        "מחפשים שותפה לדירה בשכונה ב, חדר מתפנה ב-1/8",
        True,
        "room_or_roommate_listing",
    ),
    (
        "נכנסת במקומי לחדר בדירת שותפות, 1500₪",
        True,
        "room_or_roommate_listing",
    ),

    # TRICKY: roommate keyword but full apartment — should NOT be roommate
    (
        "דירת 3 חדרים מתפנה בשכונה ב, מתאימה לזוג, 3800₪",
        True,
        "relevant_rental_apartment",
    ),

    # Should be SALE POST
    (
        "דירת 4 חדרים למכירה בשכונה ב, מחיר 1,200,000",
        True,
        "sale_post",
    ),

    # TRICKY: post contains מחפש but is NOT a seeker — landlord saying "מחפש דיירים"
    (
        "דירה להשכרה, בעל דירה מחפש דיירים טובים, 3 חדרים 3600₪",
        True,
        "relevant_rental_apartment",
    ),

    # Should be IRRELEVANT (unrelated content)
    (
        "מישהו מכיר אינסטלטור טוב בשכונה ב? צריך עזרה דחופה",
        True,
        "irrelevant",
    ),

    # ── New cases (covering gaps found in review) ──────────────────────────

    # 1.5-room apartment — within user's min_rooms=1.5 → should be relevant, not maybe
    (
        "דירת 1.5 חדרים להשכרה בשכונה ב, כניסה מיידית, 2800 ש\"ח",
        True,
        "relevant_rental_apartment",
    ),

    # Explicitly marketed to a couple → boost score, should be relevant
    (
        "דירת 2 חדרים מתפנה, מתאימה לזוג צעיר, 3600 לחודש",
        True,
        "relevant_rental_apartment",
    ),

    # Missing price — should NOT be rejected, score on other signals
    (
        "דירה להשכרה בשכונה ב, 3 חדרים, כניסה ב-1/7, בעל הדירה",
        True,
        "relevant_rental_apartment",
    ),

    # Missing neighborhood (non-dedicated group) with rental keyword → maybe
    (
        "דירה להשכרה 3 חדרים, כניסה מיידית",
        False,
        "relevant_rental_apartment",
    ),

    # Over-budget on non-dedicated group — should still be detected
    (
        "דירת 3 חדרים להשכרה, 6000 ש\"ח לחודש",
        False,
        "over_budget",
    ),

    # 5-room apartment → outside max_rooms=3.5 → maybe
    (
        "דירת 5 חדרים להשכרה בשכונה ב, 4000 לחודש",
        True,
        "maybe_relevant_rental_apartment",
    ),

    # Seeker from a couple (common pattern that was passing before)
    (
        "אנחנו זוג מחפשים דירת 3 חדרים לשכירות בשכונה ב",
        True,
        "seeker_post",
    ),

    # ── שכונה ב ONLY filter ────────────────────────────────────────────────

    # Other neighborhood (שכונה א) without ב → discard even on dedicated group
    (
        "יחידת דיור חדר וסלון רחוב ביאליק שכונה א משופצת, 2400 לחודש",
        True,
        "irrelevant",
    ),
    # שכונה ה → discard
    (
        "להשכרה בשכונה ה רחוב העליה, יחידת חדר וסלון, 2350",
        True,
        "irrelevant",
    ),
    # שכונה ו → discard
    (
        "דירת 3 חדרים להשכרה בשכונה ו החדשה, כניסה מיידית, 3500",
        True,
        "irrelevant",
    ),
    # Named other neighborhood נווה זאב → discard
    (
        "דירת 3 חדרים להשכרה בנווה זאב, משופצת, 3800 לחודש",
        True,
        "irrelevant",
    ),
    # Mentions both another hood AND שכונה ב → keep (it IS שכונה ב)
    (
        "דירת 3 חדרים להשכרה בשכונה ב, קרוב לגבול שכונה ה, 3600",
        True,
        "relevant_rental_apartment",
    ),
    # "בשכונה זו" must NOT false-match שכונה ז → stays relevant
    (
        "דירה להשכרה 3 חדרים, בשכונה זו שקט מאוד, כניסה מיידית, שכונה ב",
        True,
        "relevant_rental_apartment",
    ),
    # No couple word, but right room count → still relevant
    (
        "דירת 3 חדרים להשכרה בשכונה ב, משופצת, כניסה מיידית, 3700",
        True,
        "relevant_rental_apartment",
    ),

    # ── Food / service ads that leaked before ──────────────────────────────

    # The fruit-platter ad from the screenshot → must NOT be relevant
    (
        "סושי פירות טרי ומפנק מבית פרי פרימיום מחפשים קינוח מיוחד שיגנוב את ההצגה? "
        "סושי פירות צבעוני, טרי ומושקע, זמין למשלוח",
        True,
        "irrelevant",
    ),
    # Catering ad with availability word but no apartment context
    (
        "מגש פירות מושקע זמין לכל אירוע, הזמינו עכשיו",
        True,
        "irrelevant",
    ),
]

# ─── Run tests ────────────────────────────────────────────────────────────────

def run_tests():
    passed = 0
    failed = 0

    for text, dedicated, expected in TESTS:
        classification, score, rooms, price, reasons = classify_post(text, dedicated)
        ok = classification == expected
        mark = "OK" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        snippet = text[:70].replace('\n', ' ')
        print(f"  {mark}  [{classification:35s}] score={score:2d}  {snippet}")
        if not ok:
            print(f"       expected: {expected}")
            print(f"       reasons:  {reasons}")

    print(f"\n{'='*60}")
    print(f"  {passed}/{passed+failed} tests passed")
    if failed:
        print("  WARNING: Some tests failed — review classifier logic.")
    else:
        print("  All tests passed!")

# ─── Also test extraction helpers ─────────────────────────────────────────────

PRICE_TESTS = [
    ("שכד 3500₪ לחודש", 3500),
    ("3,500 ש\"ח", 3500),
    ("4100 כולל ארנונה", 4100),
    ("מחיר: 3800", 3800),
    ("2 חדרים בקומה 3", 0),       # should NOT extract 2 or 3 as price
    ("דירה בשנת 2022", 0),         # should NOT extract 2022 as price
]

ROOMS_TESTS = [
    ("3 חדרים", 3.0),
    ("דירת 2.5 חדרים", 2.5),
    ("2חד'", 2.0),
    ("3.5חד", 3.5),
    ("סטודיו", 0.0),               # studio doesn't extract rooms
]

def run_extraction_tests():
    print("\n-- Price extraction --")
    for text, expected in PRICE_TESTS:
        result = extract_price(text)
        ok = result == expected
        print(f"  {'OK' if ok else 'FAIL'}  extract_price({text!r:35s}) -> {result} (expected {expected})")

    print("\n-- Room extraction --")
    for text, expected in ROOMS_TESTS:
        result = extract_rooms(text)
        ok = result == expected
        print(f"  {'OK' if ok else 'FAIL'}  extract_rooms({text!r:25s}) -> {result} (expected {expected})")


if __name__ == "__main__":
    print("=" * 60)
    print("  Facebook Post Classifier — Test Suite")
    print("=" * 60)
    print()
    run_tests()
    run_extraction_tests()
