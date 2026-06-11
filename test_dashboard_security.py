"""
test_dashboard_security.py — regression tests for the stored-XSS fix.

The dashboard renders scraped/attacker-controlled listing text CLIENT-SIDE by
building HTML strings. The fix: every dynamic field must go through esc()
(HTML-escape) or safeUrl()/safeId(). These tests lock that in by asserting the
served template's JS — if someone later interpolates a raw field, a test fails.

Run:  python test_dashboard_security.py   (or: pytest test_dashboard_security.py)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import dashboard

HTML = dashboard.DASHBOARD_HTML

CHECKS = []
def check(name, cond):
    CHECKS.append((name, bool(cond)))

# ── esc() must escape all five dangerous characters ──
check("esc escapes &",  r".replace(/&/g,'&amp;')"  in HTML)
check("esc escapes <",  r".replace(/</g,'&lt;')"   in HTML)
check("esc escapes >",  r".replace(/>/g,'&gt;')"   in HTML)
check("esc escapes \"", r'.replace(/"/g,' in HTML)
check("esc escapes '",  r".replace(/'/g,'&#39;')"  in HTML)

# ── helpers exist ──
check("safeUrl() defined", "function safeUrl(" in HTML)
check("safeId() defined",  "function safeId("  in HTML)

# ── card(): dynamic fields are escaped, url validated, id sanitized ──
check("card escapes address", "esc(l.address" in HTML)
check("card escapes contact", "esc(l.contact)" in HTML)
check("card escapes preview", "esc(l.preview)" in HTML)
check("card escapes source tag", "esc(sk)" in HTML)
check("card escapes image src", "esc(l.image)" in HTML)
check("card escapes why-chips", "esc(w)" in HTML)
check("card uses safeUrl for the open link", "safeUrl(l.url)" in HTML)
check("card uses safeId for handlers", "safeId(l.id)" in HTML)

# ── archive + tips + groups + agent-status escape their text ──
check("archive escapes address", "esc(l.address||l.title" in HTML)
check("tips widget escapes title", "esc(t.title)" in HTML)
check("tips page uses safeUrl", "safeUrl(t.url)" in HTML)
check("settings groups escape name", "esc(n)" in HTML)
check("agent-status escapes detail", "esc(det)" in HTML)

# ── negative: the old RAW (unescaped) interpolations must be GONE ──
check("no raw preview render",  '<div class="prev">${l.preview}' not in HTML)
check("no raw address render",  ">${l.address||l.title||'שכונה ב׳'}<" not in HTML)
check("no raw url href",        'href="${l.url}"' not in HTML)
check("no raw image src",       'src="${l.image}"' not in HTML)
check("no raw why-chip",        '"why-chip">${w}<' not in HTML)


def main():
    print("=" * 56)
    print("  Dashboard XSS regression tests")
    print("=" * 56)
    passed = sum(1 for _, ok in CHECKS if ok)
    for name, ok in CHECKS:
        print(f"  {'OK  ' if ok else 'FAIL'}  {name}")
    print("-" * 56)
    print(f"  {passed}/{len(CHECKS)} passed")
    if passed != len(CHECKS):
        print("  WARNING: an XSS-escaping invariant regressed!")
        sys.exit(1)
    print("  All XSS regression checks passed.")


def test_xss_escaping_invariants():   # pytest entry point
    failed = [n for n, ok in CHECKS if not ok]
    assert not failed, f"XSS invariants regressed: {failed}"


if __name__ == "__main__":
    main()
