from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ga4_reporting import METRICS, _metric_map, build_snapshot, summarize_leads


def _response(dimensions=None, values=None, rows=True):
    result = {
        "metricHeaders": [{"name": name} for name in METRICS],
        "rows": [],
    }
    if rows:
        result["rows"] = [{"metricValues": [{"value": str(x)} for x in (values or [1] * len(METRICS))]}]
    if dimensions:
        result["dimensionHeaders"] = [{"name": name} for name in dimensions]
        result["rows"] = [{
            "dimensionValues": [{"value": "Organic Search"} for _ in dimensions],
            "metricValues": [{"value": "3"} for _ in METRICS],
        }] if rows else []
    return result


class _Request:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class _Properties:
    def runReport(self, property, body):
        dimensions = [item["name"] for item in body.get("dimensions", [])]
        if dimensions:
            return _Request(_response(dimensions=dimensions))
        return _Request(_response())


class _Service:
    def properties(self):
        return _Properties()


def test_metric_map_preserves_missing_rows_as_none():
    result = _metric_map(_response(rows=False))
    assert all(result[name] is None for name in METRICS)


def test_build_snapshot_compares_two_complete_seven_day_windows():
    result = build_snapshot(_Service(), "497002086", date(2026, 11, 15))
    assert result["period"] == {"start": "2026-11-09", "end": "2026-11-15"}
    assert result["previous_period"] == {"start": "2026-11-02", "end": "2026-11-08"}
    assert result["current"]["has_rows"] is True
    assert result["delta"]["activeUsers"] == 0
    assert result["property_id"] == "497002086"
    assert result["interpretation_limit"].find("not query-level") >= 0



def test_lead_crm_counts_only_recorded_inquiries_and_separates_qualified_leads_from_clients():
    from ga4_reporting import LEAD_HEADERS

    def row(**values):
        return [values.get(name, "") for name in LEAD_HEADERS]

    summary = summarize_leads([
        row(lead_ref="L-001", received_at="2026-11-16", source_platform="Google Organic", contact_method="whatsapp", lead_status="NEW"),
        row(lead_ref="L-002", received_at="2026-11-16", source_platform="Facebook", contact_method="phone", lead_status="QUALIFIED"),
        row(lead_ref="L-003", received_at="2026-11-16", source_platform="LinkedIn", contact_method="whatsapp", lead_status="CLIENT"),
        row(),
    ])
    assert summary["inquiries_received"] == 3
    assert summary["qualified_leads"] == 2
    assert summary["clients_confirmed"] == 1
    assert summary["pending_follow_up"] == 1
    assert summary["by_source_platform"] == {"Facebook": 1, "Google Organic": 1, "LinkedIn": 1}
