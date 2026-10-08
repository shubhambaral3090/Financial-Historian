"""Optional browser smoke-test entry point. Never connects to either provider."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.pop("SEC_USER_AGENT", None)

import financial_historian.market
import financial_historian.service
import financial_historian.universe
from ui_fixtures import FixtureHistorian, FixtureMarket, FixtureUniverse

FixtureHistorian.periods = 25
if os.environ.get("FISHTORIAN_RICH_FIXTURE") == "1":
    from dataclasses import replace
    from test_metrics_v06 import metric_fixture
    def rich_generate(self, company, progress=None):
        bundle = metric_fixture()
        bundle.company = replace(company, sic="3571")
        if progress:
            progress("Preparing fictional historical analysis acceptance data")
        return bundle
    FixtureHistorian.generate = rich_generate
financial_historian.service.FinancialHistorian = FixtureHistorian
financial_historian.market.YahooFinanceProvider = FixtureMarket
financial_historian.universe.UniverseProvider = FixtureUniverse
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
