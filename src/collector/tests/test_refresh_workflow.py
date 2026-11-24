from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_refresh_collects_twelve_auction_pages():
    workflow = (ROOT / ".github/workflows/refresh.yml").read_text()
    assert "--page-size 12 " in workflow
    assert "--page-size 4 " not in workflow
    assert "(12 auctions each)" in workflow
