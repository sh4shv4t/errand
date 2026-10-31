import pytest

from errand import config, db, seed


@pytest.fixture
def conn(tmp_path):
    config.configure(db_path=str(tmp_path / "errand.db"), sim_latency_scale=0.0, mystery_rate=0.0, demo=True,
                     paypal_client_id="", paypal_secret="", base_url="http://testserver")
    c = db.connect()
    db.init(c)
    yield c
    c.close()


@pytest.fixture
def seeded(conn):
    seed.seed(conn, with_ollama=False)
    return conn
