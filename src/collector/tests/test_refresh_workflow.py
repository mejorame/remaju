from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_refresh_collects_four_auction_pages():
    workflow = (ROOT / ".github/workflows/refresh.yml").read_text()
    assert "--page-size 4 " in workflow
    assert "--page-size 12 " not in workflow
    assert "(4 auctions each)" in workflow
