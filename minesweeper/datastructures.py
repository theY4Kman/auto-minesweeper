from collections import defaultdict

from .director.base import Cell


class SubsetGraph(object):
    """
    Associate an object with a list of identifying coordinates, and find other
    objects with whose coordinates are supersets or subsets.
    """

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
        shares = set()
        for coord in self._coord_sets[o]:
            shares |= self._lookup[coord]
        return shares

    def subsets_of(self, o):
        shares = self._shares(o) - {o}
        coord_set = self._coord_sets[o]
        return {s for s in shares
                if self._coord_sets[s].issubset(coord_set)}

    def supersets_of(self, o):
        shares = self._shares(o) - {o}
        coord_set = self._coord_sets[o]
        return {s for s in shares
                if self._coord_sets[s].issuperset(coord_set)}


class NeighborGraph(object):
    def __init__(self, cells=None, filter=None):
        """
        :type cells: list of Cell
        """
        if filter is None:
            filter = lambda c: True
        self.filter = filter

        iterable = None
        if cells:
            iterable = [(c, self._coord_set(c)) for c in cells]

        self._map = SubsetGraph(iterable)

    def _coord_set(self, cell):
        return [(n.x, n.y)
                for n in self.get_neighbor_cells(cell)
                if self.filter(n)]

    def get_neighbor_cells(self, cell):
        return cell.get_neighbors()

    def add(self, cell):
        self._map.add(cell, self._coord_set(cell))

    def subsets_of(self, cell):
        return self._map.subsets_of(cell)

    def supersets_of(self, cell):
        return self._map.supersets_of(cell)
