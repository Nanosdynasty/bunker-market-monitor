import pytest

from bunker_market import create_app
from bunker_market.models import db


@pytest.fixture()
def app(tmp_path):
    database = tmp_path / "test.db"
    app = create_app(
        {
            "TESTING": True,
            "ENABLE_SCHEDULER": False,
            "DEMO_MODE": False,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
            "BULUGO_API_KEY": "",
            "OILPRICEAPI_KEY": "",
        }
    )
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
