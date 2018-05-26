from collections import defaultdict
from typing import (
    Callable,
    Dict,
    Generic,
    Iterable,
    NewType,
    Set,
    Tuple,
    TypeVar,
)

from .director.base import Cell


Coord = NewType('Coord', Tuple[int, int])

Obj = TypeVar('Obj')
Prop = TypeVar('Prop')


class PropertyGraph(Generic[Obj, Prop]):
    def __init__(self, objects: Iterable[Obj]=None, get_props: Callable[[Obj], Iterable[Prop]]=None):
        self._get_props = get_props or (lambda o: ())
        self._props: Dict[Obj, Set[Prop]] = defaultdict(set)
        self._reverse: Dict[Prop, Set[Obj]] = defaultdict(set)
        self.update(objects or ())

    def update(self, objects: Iterable[Obj]):
        for o in objects:
            self.add(o)

    def difference_update(self, objects: Iterable[Obj]):
        for o in objects:
            self.remove(o)

    def add(self, o: Obj, extra_props: Iterable[Prop]=None):
        props = tuple(self._get_props(o)) + tuple(extra_props or ())
        self._props[o].update(props)
        for prop in props:
            self._reverse[prop].add(o)

    def remove(self, o: Obj):
        for prop in self.props_of(o):
            self._reverse[prop].discard(o)
        del self._props[o]

    def __iter__(self):
        return iter(self._props)

    def all_props(self) -> Set[Prop]:
        return set(self._reverse)

    def props_of(self, o: Obj) -> Set[Prop]:
        return self._props[o]

    def objects_containing(self, prop: Prop) -> Set[Obj]:
        return self._reverse[prop]

    def __contains__(self, o: Obj):
        return o in self._props

    def relatives_of(self, o: Obj) -> Set[Obj]:
        props = self.props_of(o)
        relatives = set()
        for prop in props:
            relatives |= self.objects_containing(prop)
        return relatives - {o}

    def relatives_whose_props(self, o: Obj, filter: Callable[[Set[Prop], Set[Prop]], bool]
                              ) -> Set[Obj]:
        our_props = self.props_of(o)
        return {
            relative
            for relative in self.relatives_of(o)
            if filter(our_props, self.props_of(relative))
        }

    def relatives_contained_by(self, o: Obj, strict: bool=False) -> Set[Obj]:
        return self.relatives_whose_props(o, lambda our_props, their_props: (
            their_props.issubset(our_props) and
            not (strict and their_props == our_props)
        ))

    def relatives_containing(self, o: Obj, strict: bool=False) -> Set[Obj]:
        return self.relatives_whose_props(o, lambda our_props, their_props: (
            their_props.issuperset(our_props) and
            not (strict and their_props == our_props)
        ))

    def relatives_equal_to(self, o: Obj) -> Set[Obj]:
        return self.relatives_whose_props(o, lambda our_props, their_props: (
            our_props == their_props
        ))


def graph_by(objects: Iterable[Obj],
             get_props: Callable[[Obj], Iterable[Prop]]
             ) -> PropertyGraph[Obj, Prop]:
    return PropertyGraph(objects, get_props)


class CellGraph(PropertyGraph[Cell, Coord]):
    """Relate cells by their shared neighbours

    Usage:

        graph = CellGraph(cells, lambda c: c.get_neighbors(is_unrevealed=True))

    """

    def __init__(self, cells: Iterable[Cell]=None, get_neighbors: Callable[[Cell], Iterable[Cell]]=None):
        get_neighbors = get_neighbors or (lambda c: c.get_neighbors())
        super().__init__(cells, get_neighbors)
