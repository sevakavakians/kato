from hashlib import sha1

import numpy as np
from numpy import any, array, dot, signbit, sqrt, transpose


class VectorObject:

    def __init__(self, vector):
        self.vector = vector
        self.vector_length = sqrt(dot(self.vector, self.vector.transpose()))   # vector_length used for heuristics
        self.vector_hash = str(sha1(str(self.vector).encode('utf-8')).hexdigest())
        self.name = "VECTOR|%s" %(self.vector_hash)
        return

    def __lt__(self, other):
        if isinstance(other, VectorObject):
            if self.vector_length < other.vector_length:
                return True
        return False

    def __gt__(self, other):
        if isinstance(other, VectorObject):
            if self.vector_length > other.vector_length:
                return True
        return False

    def __eq__(self, other):
        if isinstance(other, VectorObject):
            if self.vector.all == other.vector.all:
                return True
        return False

    def eqHS(self, other):
        if self.vector == other.vector:
            return True
        else:
            return False

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
        if self.vector_length == 0: # This works when using DVC since all values must be positive.
            return True
        else:
            return False

    def isLessThanZero(self):
        "Return True if any value is less than zero."
        return any(signbit(self.vector))

    def transpose(self):
        return transpose(array([self.vector]))

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
