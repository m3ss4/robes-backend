import pytest
from app.main import app
from app.auth import deps as auth_deps


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[auth_deps.get_current_user_id] = lambda: "test-user"
    app.dependency_overrides[auth_deps.get_user_id_optional] = lambda: "test-user"
    yield
    app.dependency_overrides.pop(auth_deps.get_current_user_id, None)
    app.dependency_overrides.pop(auth_deps.get_user_id_optional, None)
