import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'tests')))
from fixtures.kato_fixtures import KATOTestFixture

fixture = KATOTestFixture(processor_name="test_clear")
fixture.setup()

try:
    result = fixture.clear_all_memory()
    print(f"Clear result: '{result}'")
    print(f"Type: {type(result)}")
finally:
    fixture.teardown()
