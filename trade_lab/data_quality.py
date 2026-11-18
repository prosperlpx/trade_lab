"""Strict validation for historical research datasets.

Validation is intentionally non-repairing: research inputs are never silently
sorted, deduplicated, or filled before they are fingerprinted and simulated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .data import OHLCV

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class DataFinding:
    code: str
    severity: Severity
    message: str
    count: int = 1


def validate_research_bars(
    bars: pd.DataFrame,
    *,
    expected_interval_minutes: int | None = None,
) -> list[DataFinding]:
    """Inspect raw OHLCV bars without mutating or repairing the input."""
    findings: list[DataFinding] = []
    missing = [column for column in OHLCV if column not in bars.columns]
    if missing:
        return [
            DataFinding("missing_columns", "error", f"Missing columns: {missing}", len(missing))
        ]

    if not isinstance(bars.index, pd.DatetimeIndex):
        return [DataFinding("invalid_index", "error", "Index must be a DatetimeIndex")]
    if bars.index.tz is None:
        return [DataFinding("naive_timestamps", "error", "Timestamps must include a timezone")]
    if bars.index.isna().any():
        findings.append(DataFinding(
            "missing_timestamps", "error", "Datetime values cannot be missing",
            int(bars.index.isna().sum()),
        ))
    if bars.index.has_duplicates:
        findings.append(DataFinding(
            "duplicate_timestamps", "error", "Duplicate timestamps are not permitted",
            int(bars.index.duplicated(keep=False).sum()),
        ))
    if not bars.index.is_monotonic_increasing:
        findings.append(DataFinding(
            "unordered_timestamps", "error", "Timestamps must be strictly increasing"
        ))

    numeric = bars[OHLCV].apply(pd.to_numeric, errors="coerce")
    invalid = ~pd.Series(
        np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1), index=bars.index
    )
    if invalid.any():
        findings.append(DataFinding(
            "non_finite_values", "error", "OHLCV contains missing or non-finite values",
            int(invalid.sum()),
        ))

    valid_rows = numeric.loc[~invalid]
    if not valid_rows.empty:
        bad_price = (
            (valid_rows[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
            | (valid_rows["High"] < valid_rows[["Open", "Low", "Close"]].max(axis=1))
            | (valid_rows["Low"] > valid_rows[["Open", "High", "Close"]].min(axis=1))
        )
        if bad_price.any():
            findings.append(DataFinding(
                "invalid_ohlc", "error", "Prices must be positive and High/Low must enclose OHLC",
                int(bad_price.sum()),
            ))
        negative_volume = valid_rows["Volume"] < 0
        if negative_volume.any():
            findings.append(DataFinding(
                "negative_volume", "error", "Volume cannot be negative",
                int(negative_volume.sum()),
            ))

    if expected_interval_minutes is not None:
        if (
            isinstance(expected_interval_minutes, bool)
            or not isinstance(expected_interval_minutes, int)
            or expected_interval_minutes < 1
        ):
            findings.append(DataFinding(
                "invalid_expected_interval", "error",
                "expected_interval_minutes must be a positive integer",
            ))
        elif len(bars.index) > 1 and bars.index.is_monotonic_increasing:
            utc_index = bars.index.tz_convert("UTC")
            local_dates = utc_index.tz_convert("America/New_York").date
            deltas = utc_index.to_series().diff().dt.total_seconds().div(60)
            # Only flag gaps within the same New York calendar date. Overnight,
            # weekends, holidays, and early closes require an exchange calendar.
            same_session_date = pd.Series(local_dates, index=utc_index).eq(
                pd.Series(local_dates, index=utc_index).shift()
            )
            gaps = same_session_date & (deltas > expected_interval_minutes * 1.5)
            if gaps.any():
                findings.append(DataFinding(
                    "intraday_gaps", "warning",
                    "Unexpected intraday timestamp gaps detected; "
                    "verify against the venue calendar",
                    int(gaps.sum()),
                ))

    return findings


def findings_as_dicts(findings: list[DataFinding]) -> list[dict[str, object]]:
    """Return JSON-ready validation findings."""
    return [asdict(finding) for finding in findings]


def has_errors(findings: list[DataFinding]) -> bool:
    return any(finding.severity == "error" for finding in findings)
