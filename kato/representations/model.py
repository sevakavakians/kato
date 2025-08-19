from hashlib import sha1

class Model:
    """
    Model Objects are a time-ordered list of State models.
    ex:
        model = [['A'],['B'],['c1', c2'],['D']]
    """
    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.length = sum(len(x) for x in self.sequence)
        self.name = sha1(('%s' %self.sequence).encode('utf-8')).hexdigest()
        return

    def __repr__(self):
        return """<Model|%s>""" %(self.name)

    def __len__(self):
        "Number of symbols."
        return self.length
