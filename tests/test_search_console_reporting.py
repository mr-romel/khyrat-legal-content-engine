from search_console_sitemap import query_name_visibility, NAME_VARIANTS, CONTENT_GROUPS


class _Request:
    def __init__(self, phrase):
        self.phrase = phrase

    def execute(self):
        if self.phrase == "محمود خيرت":
            return {"rows": [
                {"keys": ["محمود خيرت المحامي"], "clicks": 2, "impressions": 10, "ctr": 0.2, "position": 3.0},
                {"keys": ["محمود خيرت"], "clicks": 1, "impressions": 5, "ctr": 0.2, "position": 5.0},
            ]}
        return {"rows": []}


class _SearchAnalytics:
    def query(self, siteUrl, body):
        phrase = body["dimensionFilterGroups"][0]["filters"][0]["expression"]
        assert body["startDate"] and body["endDate"]
        assert body["dimensions"] == ["query"]
        return _Request(phrase)


class _Client:
    def searchanalytics(self):
        return _SearchAnalytics()


def test_visibility_report_covers_identity_and_legal_topic_groups():
    report = query_name_visibility(_Client())
    assert [row["phrase"] for row in report["phrases"]] == NAME_VARIANTS
    assert [row["phrase"] for row in report["contentGroups"]] == CONTENT_GROUPS
    identity = next(row for row in report["phrases"] if row["phrase"] == "محمود خيرت")
    assert identity["clicks"] == 3
    assert identity["impressions"] == 15
    assert identity["averagePosition"] == (3 * 10 + 5 * 5) / 15
    assert any("overlap" in note.lower() for note in report["measurementNotes"])
    assert all("dataAvailable" in row for row in report["phrases"] + report["contentGroups"])
