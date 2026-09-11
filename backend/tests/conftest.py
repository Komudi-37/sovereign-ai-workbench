import pytest
from app.db.init_db import init_database

@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Ensure database tables exist before any tests run."""
    init_database()
