import functools
from hashlib import sha1
from itertools import chain


class Pattern:
    """
    Pattern Objects represent learned structures that can be:
    1. Temporal patterns (sequences) - time-ordered with temporal dependency
    2. Profile patterns - collections without temporal dependency or ordering

    Pattern data is stored as a list of event groups.
    ex:
        pattern = [['A'],['B'],['c1', c2'],['D']]
    """
    def __init__(self, pattern_data):
        self.pattern_data = list(pattern_data)
        self.length = sum(len(x) for x in self.pattern_data)
        self.name = sha1(('{}'.format(self.pattern_data)).encode('utf-8'), usedforsecurity=False).hexdigest()
        return

    @functools.cached_property
    def flat_data(self) -> list[str]:
        """Flattened pattern_data as a single list of symbols. Cached on first access."""
        return list(chain(*self.pattern_data))

    def __repr__(self):
        return """<PTRN|{}>""".format(self.name)

    def __len__(self):
        "Number of symbols in the pattern."
        return self.length
