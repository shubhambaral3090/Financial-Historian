from financial_historian.universe import UniverseProvider


def test_universe_merges_duplicate_membership_and_preserves_sources():
    tables = {
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies": [
            {"Symbol": "ABC", "Security": "Example Co", "CIK": "123"},
        ],
        "https://en.wikipedia.org/wiki/Nasdaq-100": [
            {"Ticker": "ABC", "Company": "Example Co", "CIK number": "123"},
            {"Ticker": "XYZ", "Company": "Other Co", "CIK number": "456"},
        ],
    }
    provider = UniverseProvider(lambda url: tables[url])
    members = provider.load()
    assert len(members) == 2
    example = next(member for member in members if member.company.ticker == "ABC")
    assert example.indexes == ("Nasdaq-100", "S&P 500")
    assert example.company.cik == "0000000123"
    assert example.source_url.startswith("https://en.wikipedia.org")


def test_universe_sorting_is_stable_and_company_search_data_is_clean():
    tables = {
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies": [{"Symbol": "b.b", "Security": "Beta", "CIK": "2"}],
        "https://en.wikipedia.org/wiki/Nasdaq-100": [{"Ticker": "A", "Company": "Alpha", "CIK number": "1"}],
    }
    members = UniverseProvider(lambda url: tables[url]).load()
    assert [m.company.ticker for m in members] == ["A", "B-B"]
    assert [m.company.cik for m in members] == ["0000000001", "0000000002"]
