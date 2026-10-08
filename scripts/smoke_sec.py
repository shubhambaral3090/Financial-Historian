"""Optional live workflow check, using a privately configured SEC contact."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from financial_historian.export import build_workbook
from financial_historian.models import STATEMENTS
from financial_historian.sec_client import SecAccessError
from financial_historian.service import FinancialHistorian


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contact = os.environ.get("SEC_USER_AGENT", "")
    if not contact:
        print("Set SEC_USER_AGENT privately for this optional live check. Browser-session contact is not stored in files.")
        return 1
    try:
        service = FinancialHistorian(contact)
        companies = service.search_companies(args.ticker)
        if not companies:
            print("No matching SEC company was found.")
            return 1
        exact = [c for c in companies if c.ticker.upper().replace('.', '-') == args.ticker.upper().replace('.', '-')]
        if len(exact) != 1:
            print("No unique exact SEC ticker match was found.")
            return 1
        company = service.resolve_company(exact[0])
        bundle = service.generate(company, progress=print)
        data = build_workbook(bundle)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output = args.output or Path("exports") / f"{company.cik}_{stamp}_live_check.xlsx"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(data)
        complete = all(any(row.values for row in bundle.statements[s]) for s in STATEMENTS)
        print(f"{company.name}: {len(bundle.filings)} annual filings, {len(bundle.periods)} period columns.")
        print(f"Saved {output}. Read Sources & Coverage to assess extraction gaps.")
        if not complete:
            print("Live check incomplete: one or more statements contain no financial values.")
            return 2
        print("Live retrieval and export completed; this does not certify complete lifetime coverage.")
        return 0
    except (SecAccessError, ValueError):
        print("Live check failed. Verify SEC contact, internet access and the app's diagnostic log.")
        return 1
    except FileExistsError:
        print("The output file already exists. Choose a different output path.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
