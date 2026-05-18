def test_db_url_present():
    from config.config import DB_URL
    assert DB_URL.startswith("mysql+asyncmy://")
