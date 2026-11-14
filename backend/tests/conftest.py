import pytest

from backend.app import simulator
from backend.app.sensors import Simulation


@pytest.fixture(autouse=True)
def isolated_simulator():
    fresh = Simulation()
    for field in type(fresh).model_fields:
        setattr(simulator.state, field, getattr(fresh, field))
    yield
