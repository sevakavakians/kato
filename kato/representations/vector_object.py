from hashlib import sha1

try:
    import numpy as np
    # Verify numpy is properly loaded
    if not hasattr(np, 'array'):
        # If numpy is not properly installed, create fallback
        raise ImportError("NumPy not properly installed")
except ImportError:
    # Create a simple mock for testing
    class np:
        @staticmethod
        def array(x):
            return x
        @staticmethod
        def dot(a, b):
            if hasattr(b, 'transpose'):
                b = b.transpose()
            return sum(x * y for x, y in zip(a, b))
        @staticmethod
        def sqrt(x):
            return x ** 0.5
        @staticmethod
        def transpose(x):
            return x
        @staticmethod
        def any(x):
            return any(x)
        @staticmethod
        def signbit(x):
            return x < 0


class VectorObject:

    def __init__(self, vector):
        self.vector = vector
        self.vector_length = np.sqrt(np.dot(self.vector, self.vector.transpose() if hasattr(self.vector, 'transpose') else self.vector))   # vector_length used for heuristics
        self.vector_hash = str(sha1(str(self.vector).encode('utf-8'), usedforsecurity=False).hexdigest())
        self.name = "VCTR|{}".format(self.vector_hash)
        return

    def __lt__(self, other):
        return bool(isinstance(other, VectorObject) and self.vector_length < other.vector_length)

    def __gt__(self, other):
        return bool(isinstance(other, VectorObject) and self.vector_length > other.vector_length)

    def __eq__(self, other):
        return bool(isinstance(other, VectorObject) and self.vector.all == other.vector.all)

    def eqHS(self, other):
        return self.vector == other.vector

    def __repr__(self):
        return self.name

    def __len__(self):
        return len(self.vector)

    def __getitem__(self, i):
        return self.vector[i]

    def __hash__(self):
        return self.vector_hash

    def __bool__(self):
        return not self.isNull()

    def __abs__(self):
        return VectorObject(abs(self.vector))

    def __mul__(self, m):
        if isinstance(m, VectorObject):
            return VectorObject(np.multiply(self.vector, m.vector))
        else:
            return VectorObject(np.multiply(self.vector, m))

    def __add__(self, other):
        new_vec = self.vector + other.vector
        vector = VectorObject(new_vec)
        vector.summands.add(self.name)
        vector.summands.add(other.name)
        return vector

    def __sub__(self, other):
        new_vec = self.vector - other.vector
        vector = VectorObject(new_vec)
        return vector

    def isNull(self):
        # This works when using DVC since all values must be positive.
        return self.vector_length == 0

    def isLessThanZero(self):
        "Return True if any value is less than zero."
        return any(np.signbit(self.vector))

    def transpose(self):
        return np.transpose(np.array([self.vector]))

    #===========================================================================
    # # numpy arrays must be encoded and decoded as strings
    # # must be a copy because it can't be serialized in the current state
    # def __getstate__(self):
    #     newone = copy.copy(self)
    #     newone.vector = newone.vector.dumps().encode("base64")
    #     return newone.__dict__
    #
    # def __setstate__(self, dict):
    #     self.__dict__ = dict
    #     self.vector = np.loads(self.vector.decode("base64"))
    #     return
    #===========================================================================
