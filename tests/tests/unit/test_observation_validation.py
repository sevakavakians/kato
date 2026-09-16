"""Guards for ObservationProcessor.validate_observation.

Every raise site used to pass the message positionally *and* ``field_name`` as
a keyword. ValidationError's first positional parameter is ``field_name``, so
those calls raised ``TypeError: got multiple values for argument 'field_name'``
instead of the intended ValidationError -- meaning validation failures could
never be reported as validation failures. It went unnoticed because the error
handlers were not registered either, so everything became a 500 regardless.
"""

import pytest

from kato.exceptions import ValidationError
from kato.workers.observation_processor import ObservationProcessor


@pytest.fixture
def validator():
    # validate_observation only reads its argument, so no collaborators needed.
    return ObservationProcessor.__new__(ObservationProcessor)


@pytest.mark.parametrize("data,expected_field", [
    ({"unique_id": ""}, "unique_id"),
    ({}, "unique_id"),
    ({"unique_id": "x", "strings": "not-a-list"}, "strings"),
    ({"unique_id": "x", "strings": [1]}, "strings[0]"),
    ({"unique_id": "x", "vectors": "not-a-list"}, "vectors"),
    ({"unique_id": "x", "vectors": ["not-a-list"]}, "vectors[0]"),
    ({"unique_id": "x", "vectors": [["a"]]}, "vectors[0]"),
    ({"unique_id": "x", "emotives": "not-a-dict"}, "emotives"),
    ({"unique_id": "x", "metadata": "not-a-dict"}, "metadata"),
])
def test_invalid_observations_raise_validation_error(validator, data, expected_field):
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_observation(data)

    exc = exc_info.value
    assert exc.error_code == "VALIDATION_ERROR"
    assert exc.field_name == expected_field
    assert exc.message, "ValidationError must carry a human-readable message"


def test_valid_observation_passes(validator):
    validator.validate_observation({
        "unique_id": "obs-1",
        "strings": ["alpha", "beta"],
        "vectors": [[0.1, 0.2]],
        "emotives": {"joy": 0.5},
        "metadata": {"source": "test"},
    })
