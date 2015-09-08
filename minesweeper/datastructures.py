from collections import defaultdict


class SubsetMap(object):
    """Associate a list of coords w/ an object, find sub/supersets"""

    def __init__(self, iterable=None):
        self._coord_sets = {}
        self._lookup = defaultdict(set)

        if iterable:
            for o, coord_set in iterable:
                self.add(o, coord_set)

    def add(self, o, coord_set):
        self._coord_sets[o] = set(coord_set)
        for coord in coord_set:
            self._lookup[coord].add(o)

    def _shares(self, o):
        coord_set = self._coord_sets[o]
        return reduce(set.union, (self._lookup[c] for c in coord_set), set())

    def subsets(self, o):
        shares = self._shares(o)
        coord_set = self._coord_sets[o]
        return [s for s in shares
                if s is not o and self._coord_sets[s].issubset(coord_set)]

    def supersets(self, o):
        shares = self._shares(o)
        coord_set = self._coord_sets[o]
        return [s for s in shares
                if s is not o and self._coord_sets[s].issuperset(coord_set)]


class NeighborMap(object):
    def __init__(self, cells=None, filter=None):
        if filter is None:
            filter = lambda c: c
        self.filter = filter

        iterable = None
        if cells:
            iterable = [(c, self._coord_set(c)) for c in cells]

        self._map = SubsetMap(iterable)

    def _coord_set(self, cell):
        return [(n.x, n.y) for n in cell.get_neighbors() if self.filter(n)]

    def add(self, cell):
        self._map.add(cell, self._coord_set(cell))

    def subsets(self, cell):
        return self._map.subsets(cell)

    def supersets(self, cell):
        return self._map.supersets(cell)
