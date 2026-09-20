from runner.smoke import get_smoke_status, smoke_ping


def test_smoke_status():
    result = get_smoke_status()
    assert result["status"] == "ok"


def test_smoke_ping():
    result = smoke_ping()
    assert result == "pong"