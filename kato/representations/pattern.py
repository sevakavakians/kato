from hashlib import sha1


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

    def __repr__(self):
        return """<PTRN|{}>""".format(self.name)

    def __len__(self):
        "Number of symbols in the pattern."
        return self.length
