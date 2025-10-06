"""JSON data packaging utilities for KATO.

Provides simple serialization and deserialization functions for converting
Python objects to/from JSON format for storage and transmission.
"""

import json
from typing import Any, Union


def pack(data: Any) -> str:
    """Serialize Python data to JSON string.

    Converts Python objects (dict, list, primitives) to JSON format
    for storage or network transmission.

    Args:
        data: Any JSON-serializable Python object (dict, list, str, int, float, bool, None).

    Returns:
        JSON string representation of the data.

    Raises:
        TypeError: If data contains non-serializable objects.
        ValueError: If data contains circular references.

    Example:
        >>> pack({'name': 'test', 'value': 42})
        '{"name": "test", "value": 42}'
        >>> pack([1, 2, 3])
        '[1, 2, 3]'
    """
    return json.dumps(data)


def unpack(data: Union[str, bytes]) -> Any:
    """Deserialize JSON string to Python data.

    Converts JSON formatted string back to Python objects
    for processing within the application.

    Args:
        data: JSON string or bytes to deserialize.

    Returns:
        Python object (dict, list, str, int, float, bool, None) parsed from JSON.

    Raises:
        JSONDecodeError: If data is not valid JSON format.
        TypeError: If data is not a string or bytes.

    Example:
        >>> unpack('{"name": "test", "value": 42}')
        {'name': 'test', 'value': 42}
        >>> unpack('[1, 2, 3]')
        [1, 2, 3]
    """
    return json.loads(data)
