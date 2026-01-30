import os

import pytest


@pytest.mark.skipif(not os.getenv("TEST_OUTFIT_PHOTO_FLOW"), reason="requires db and fixtures")
def test_outfit_photo_flow_placeholder():
    # Placeholder for integration test in environments with DB + R2 fixtures.
    assert True
