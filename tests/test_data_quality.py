import pandas as pd

from trade_lab.data_quality import has_errors, validate_research_bars


def bars():
    index = pd.date_range("2026-01-05 14:30", periods=3, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 100.5, 101.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 100.5],
            "Close": [100.5, 101.0, 102.0],
            "Volume": [1000.0, 1100.0, 900.0],
        },
        index=index,
    )


def test_valid_bars_have_no_findings():
    assert validate_research_bars(bars(), expected_interval_minutes=5) == []


def test_duplicate_and_unordered_timestamps_are_errors():
    frame = bars()
    frame.index = pd.DatetimeIndex(
        [frame.index[0], frame.index[0], frame.index[2]], name="Datetime"
    )
    findings = validate_research_bars(frame)
    assert has_errors(findings)
    assert {finding.code for finding in findings} >= {"duplicate_timestamps"}


def test_invalid_ohlc_and_negative_volume_are_errors():
    frame = bars()
    frame.iloc[1, frame.columns.get_loc("High")] = 98.0
    frame.iloc[2, frame.columns.get_loc("Volume")] = -1.0
    findings = validate_research_bars(frame)
    assert {finding.code for finding in findings} >= {"invalid_ohlc", "negative_volume"}


def test_missing_and_non_finite_values_are_errors():
    frame = bars()
    frame.iloc[1, frame.columns.get_loc("Close")] = float("nan")
    findings = validate_research_bars(frame)
    assert "non_finite_values" in {finding.code for finding in findings}


def test_intraday_gap_is_warning_not_automatic_rejection():
    frame = bars().iloc[[0, 2]]
    findings = validate_research_bars(frame, expected_interval_minutes=5)
    assert not has_errors(findings)
    assert any(finding.code == "intraday_gaps" for finding in findings)


def test_missing_timestamps_are_errors():
    frame = bars()
    frame.index = pd.DatetimeIndex([frame.index[0], pd.NaT, frame.index[2]])
    findings = validate_research_bars(frame)
    assert "missing_timestamps" in {finding.code for finding in findings}
