"""Position sizing strategies."""

from __future__ import annotations


def fixed_fractional(
    account_value: float,
    risk_pct: float,
    risk_per_unit: float,
    contract_multiplier: int = 1,
) -> int:
    """Return integer position size targeting `risk_pct` of account.

    `risk_per_unit` is the per-share or per-contract dollar risk
    (entry - stop, in absolute terms). `contract_multiplier` is 100 for
    standard US equity options, 1 for shares.
    """
    if risk_per_unit <= 0 or account_value <= 0 or risk_pct <= 0:
        return 0
    risk_dollars = account_value * (risk_pct / 100.0)
    units = risk_dollars / (risk_per_unit * contract_multiplier)
    return max(0, int(units))


def kelly_fraction(win_rate: float, win_loss_ratio: float) -> float:
    """Classic Kelly: f* = W - (1-W)/R.

    `win_rate` is the historical hit rate (0..1).
    `win_loss_ratio` is avg_win / avg_loss (in absolute terms).
    Returns the suggested fraction of bankroll; clipped to [0, 1].
    """
    if win_loss_ratio <= 0:
        return 0.0
    f = win_rate - (1.0 - win_rate) / win_loss_ratio
    return max(0.0, min(1.0, f))


def kelly_position_size(
    account_value: float,
    win_rate: float,
    win_loss_ratio: float,
    risk_per_unit: float,
    fraction_of_kelly: float = 0.25,
    contract_multiplier: int = 1,
) -> int:
    """Position size using a fractional-Kelly bet on the account."""
    if account_value <= 0 or risk_per_unit <= 0:
        return 0
    full_kelly = kelly_fraction(win_rate, win_loss_ratio)
    used = full_kelly * max(0.0, min(1.0, fraction_of_kelly))
    risk_dollars = account_value * used
    if risk_dollars <= 0:
        return 0
    units = risk_dollars / (risk_per_unit * contract_multiplier)
    return max(0, int(units))
