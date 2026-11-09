"""A price must be printed with enough digits to still be that price.

THE DEFECT, seen on a bulletin the owner actually received:

    CoinGecko     DEGEN  $0.00079304
    our bulletin  DEGEN  $0.0008

`f"{val:,.4f}"` prints four DECIMAL places. Right for ETH at $2,090.77, and it
destroys a sub-cent token: 0.00079304 printed as 0.0008 is a 0.88% error, on a
number we SELL as a trading signal. Worse, and measured: a price of 0.00000008
printed as **0.0000** — the bulletin stated a price of zero for a token that has
one.

Four decimals was a formatting choice made for one token and applied to all of
them. The magnitude now decides.
"""

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent
       / "services" / "telegram_sales.py").read_text(encoding="utf-8")


def _bulletins_fmt():
    """The `_fmt` defined inside `send_market_bulletin`, lifted for testing.

    It is a closure over nothing, so the honest way to test the REAL one is to
    execute the source rather than to re-type it — a copy would pass while the
    shipped formatter stayed wrong.
    """
    start = SRC.index("    def _fmt(val, suffix=\"\"):")
    end = SRC.index("    def _fmt_change(", start)
    body = SRC[start:end]
    # De-indent one level so it can be exec'd at module scope.
    body = "\n".join(line[4:] if line.startswith("    ") else line
                     for line in body.splitlines())
    ns: dict = {}
    exec(compile(body, "<bulletin _fmt>", "exec"), ns)  # noqa: S102
    return ns["_fmt"]


FMT = _bulletins_fmt()


# ── the defect itself ───────────────────────────────────────────────────────

def test_a_sub_cent_price_keeps_its_significant_digits():
    """THE regression. 0.0008 is a different number from 0.00079304."""
    got = FMT(0.00079304)
    assert got == "0.00079304", got
    assert abs(float(got) - 0.00079304) < 1e-12, (
        "the printed price is not the price: %s" % got)


def test_a_price_is_never_printed_as_zero():
    """The worst version of the same fault: 8e-08 printed as 0.0000 states a
    price of zero, which is not a rounding error, it is a different fact."""
    got = FMT(0.00000008)
    assert float(got) != 0.0, "a token with a real price was shown as zero"
    assert got == "0.00000008", got


def test_a_large_price_is_not_saddled_with_noise():
    """The fix must not turn 2,090.77 into 2,090.77000000."""
    assert FMT(2090.77) == "2,090.77"


def test_a_mid_price_keeps_four_places():
    assert FMT(1.2345678) == "1.2346"


def test_trailing_zeros_are_trimmed_but_the_value_is_kept():
    assert FMT(0.003) == "0.003"
    assert FMT(0.0008) == "0.0008"
    assert float(FMT(0.003)) == 0.003


# ── the surrounding contract, unchanged ─────────────────────────────────────

def test_none_is_still_na():
    """An unmeasured price must never become a number. This is the same rule the
    whole codebase keeps, and the rewrite must not have broken it."""
    assert FMT(None) == "N/A"


def test_a_non_float_passes_through():
    assert FMT("1234.5") == "1234.5"


def test_the_suffix_still_applies():
    assert FMT(2090.77, " USD") == "2,090.77 USD"
    assert FMT(0.00079304, " USDC") == "0.00079304 USDC"


def test_the_formatter_is_still_used_for_both_tokens():
    """A formatter nobody calls fixes nothing."""
    for token in ("eth_price", "degen_price"):
        assert "_fmt(%s)" % token in SRC, "%s is no longer formatted" % token
    assert "_fmt_change(" in SRC


def test_no_fixed_decimal_format_survives_in_the_bulletin_formatter():
    """The exact expression that caused this, gone."""
    assert 'f"{val:,.4f}{suffix}"' not in SRC, (
        "the fixed four-decimal format is back, and it prints sub-cent prices "
        "wrong by up to a hundred percent")
    assert re.search(r"def _fmt\(val", SRC)
