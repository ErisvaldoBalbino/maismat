import pytest

from maismat import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite"), "SECRET_KEY": "test"})


@pytest.fixture
def client(app):
    return app.test_client()
