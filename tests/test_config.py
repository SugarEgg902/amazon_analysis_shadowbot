import os
import importlib


def test_db_url_default():
    """Default DB_URL uses asyncmy driver pointing to localhost."""
    env_backup = os.environ.pop("MP_AGENT_DB_URL", None)
    try:
        import config.config as cfg
        importlib.reload(cfg)
        assert cfg.DB_URL.startswith("mysql+asyncmy://")
        assert "localhost" in cfg.DB_URL
    finally:
        if env_backup is not None:
            os.environ["MP_AGENT_DB_URL"] = env_backup


def test_db_url_env_override():
    """MP_AGENT_DB_URL env var overrides the default."""
    custom = "mysql+asyncmy://user:pass@db-host:3306/mydb"
    os.environ["MP_AGENT_DB_URL"] = custom
    try:
        import config.config as cfg
        importlib.reload(cfg)
        assert cfg.DB_URL == custom
    finally:
        del os.environ["MP_AGENT_DB_URL"]
        import config.config as cfg
        importlib.reload(cfg)
