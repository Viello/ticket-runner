from runner.smoke import get_smoke_status


def test_smoke_status():
    result = get_smoke_status()
    assert result["status"] == "ok"