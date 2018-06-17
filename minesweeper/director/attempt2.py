import logging
import operator
from copy import copy
from functools import reduce
from itertools import chain
from typing import Iterable, Tuple, Set, Optional, Union, Any

from minesweeper.datastructures import PropertyGraph
from minesweeper.director.base import Director, Cell, register_director

logger = logging.getLogger(__name__)


class Group:
    """A set of cells and the known number of mines among them"""

    def __init__(self, num_mines: Union[float, int], unrevealed_cells: Iterable[Cell]):
        self.num_mines = num_mines
        self.cells = frozenset(unrevealed_cells)

    def __repr__(self):
        return f'{self.__class__.__name__}{repr(self.deconstruct())}'

    def deconstruct(self):
        return self.num_mines, self.cells

    def __hash__(self):
        return hash(self.deconstruct())

    def __eq__(self, other: 'Group'):
        assert isinstance(other, Group)
        return self.deconstruct() == other.deconstruct()

    def __len__(self):
        return len(self.cells)

    @property
    def probability(self):
        return self.num_mines / len(self)

    def difference(self, other: 'Group') -> 'Group':
        assert other.cells
        assert other.cells.issubset(self.cells)
        assert self.num_mines - other.num_mines >= 0
        return Group(self.num_mines - other.num_mines, self.cells - other.cells)

    def __sub__(self, other: 'Group') -> 'Group':
        return self.difference(other)

    def remove_possibilities(self, cells: Iterable[Cell]) -> 'Group':
        """Remove unrevealed cells from the group"""
        cells = frozenset(cells)
        assert cells
        assert len(self.cells) - len(cells) >= self.num_mines
        return Group(self.num_mines, self.cells - cells)

    def __xor__(self, other):
        assert isinstance(other, Group)
        return self.remove_possibilities(other.cells)


class GroupGraph(PropertyGraph[Group, Cell]):
    """Relate groups by the cells they refer to"""

    def __init__(self, groups: Iterable[Group] = None):
        super().__init__(groups, lambda group: group.cells)


UNSET = object()


class System(frozenset):
    """A set of cells which are completely independent of other board cells"""

    __slots__ = ('unrevealed', 'edges', 'minimum', 'maximum', 'groups')

    def __new__(cls, unrevealed: Iterable[Cell], edges: Iterable[Cell], *args, **kwargs):
        return super().__new__(cls, chain(unrevealed, edges))

    def __init__(self,
                 unrevealed: Iterable[Cell], edges: Iterable[Cell],
                 minimum: int=None, maximum: int=None,
                 groups=()):
        self.unrevealed = frozenset(unrevealed)
        self.edges = frozenset(edges)
        self.minimum = 0 if minimum is None else minimum
        self.maximum = len(self.unrevealed) if maximum is None else maximum
        self.groups = frozenset(groups or ())
        super(System, self).__init__()

    def __copy__(self):
        return self.__class__(self.unrevealed, self.edges,
                              minimum=self.minimum, maximum=self.maximum,
                              groups=self.groups)

    def __hash__(self):
        return hash((frozenset(self), self.minimum, self.maximum, self.groups))

    @classmethod
    def trace(cls, start: Cell, maximum=None) -> 'System':
        """Find all cells of a system, given an unrevealed cell"""
        assert start.is_unrevealed()  # sanity check

        unrevealed = set()
        edges = set()

        walked = set()
        unrevealed_queue = {start}
        number_queue = set()

        while unrevealed_queue or number_queue:
            walked |= unrevealed_queue | number_queue
            unrevealed |= unrevealed_queue
            edges |= number_queue

            all_queued = unrevealed_queue | number_queue
            number_queue = {
                neighbor
                for cell in unrevealed_queue
                for neighbor in cell.get_neighbors(is_number=True)
            } - walked
            unrevealed_queue = {
                neighbor
                for cell in all_queued
                for neighbor in cell.get_neighbors(is_unrevealed=True)
            } - walked

        system = cls(unrevealed, edges, maximum=maximum)
        system.groups = frozenset(cls.find_visible_groups(system))

        return system

    @staticmethod
    def find_visible_groups(cells) -> Iterable[Group]:
        """Find groups by naively matching numbers to their unrevealed neighbours

        This method may return subsets or duplicates of other groups.
        """
        cells = tuple(cells)
        remaining_unrevealed = {cell for cell in cells if cell.is_unrevealed()}
        numbered = {cell for cell in cells if cell.is_number()}

        for cell in numbered:
            unrevealed = cell.get_neighbors(is_unrevealed=True)
            if not unrevealed:
                continue

            yield Group(cell.num_flags_left, unrevealed)
            remaining_unrevealed.difference_update(unrevealed)

        if remaining_unrevealed:
            # XXX: this may not accurately represent the number of mines left in
            #      the unrevealed cells which don't touch a number.
            # Is there any more informed way to set this?
            # Does it matter, pragmatically?
            # Is there a way to refactor, such that the pragmatics match the semantics?
            yield Group(float('Inf'), remaining_unrevealed)

    def simplify(self, maximum: int=None) -> 'System':
        """Return a more compact representation of the system, if possible
        """
        system = copy(self)
        if maximum is not None:
            system.maximum = maximum

        graph = GroupGraph(system.groups)

        clean = False
        while not clean:
            clean = True

            groups: Iterable[Group] = sorted(graph, key=len)
            for group in groups:
                contained_groups = graph.relatives_contained_by(group)

                if contained_groups:
                    clean = False

                    for contained in contained_groups:
                        if contained.probability == group.probability:
                            graph.remove(contained)

                        elif contained.probability == 0:
                            graph.remove(group)
                            graph.add(group ^ contained)

                        else:
                            # XXX: I assume this will throw if game state is impossible...
                            #      Let's hope this comment doesn't go stale.
                            #      Oh, mother, tell your children not to do what I have done.
                            #      Spend your life in putoffance and technical debt
                            #      In the house of the rising-- oh shit, it's 5AM already?
                            graph.remove(group)
                            graph.add(group - contained)

        independents = {group
                        for group in graph.get_independent_objects()
                        if group.num_mines < float('inf')}
        independent_mines = sum(independent.num_mines for independent in independents)
        if independent_mines == system.maximum:
            other_groups = set(graph) - independents
            other_cells = {cell for group in other_groups for cell in group.cells}
            if other_cells:
                graph = GroupGraph(independents | {Group(0, other_cells)})

        system.groups = frozenset(graph)
        return system


def flatten_groups(groups: Iterable[Group]) -> Iterable[Tuple[float, Cell]]:
    """Determine probability of each cell using info from the passed groups
    """
    graph = GroupGraph(groups)
    for cell in graph.all_props():
        containers = graph.objects_containing(cell)
        yield max(group.probability for group in containers), cell


def exec_moves(moves: Iterable[Union[Tuple[str, Cell], Tuple[str, Cell, Any]]],
               extra_message=''):
    """Execute a list of moves
    """
    for row in moves:
        try:
            method_name, cell = row
        except ValueError:
            method_name, cell, message = row
        else:
            message = ''

        method = getattr(cell, method_name)
        method()

        # XXX: heuristic
        if 'mark' not in method_name:
            logger.debug('%12s %-3d %-3d %s %s',
                         method_name.upper(), cell.x, cell.y, message, extra_message)


def find_systems(cells: Iterable[Cell], maximum: int=None) -> Iterable[System]:
    """Find all groups of cells separated from other groups
    """
    cells = {cell for cell in cells if cell.is_unrevealed()}

    while cells:
        system = System.trace(cells.pop(), maximum=maximum)
        yield system
        cells -= system.unrevealed


def split_moves(groups: Iterable[Group]
                ) -> Tuple[Iterable[Tuple[str, Cell, str]],
                           Iterable[Tuple[float, Cell]]]:
    moves = []
    probabilities = []
    for probability, cell in flatten_groups(groups):
        if probability == 1:
            moves.append(('right_click', cell, 'FLAG'))
        elif probability == 0:
            moves.append(('click', cell, 'REVEAL'))
        else:
            probabilities.append((probability, cell))
    return moves, probabilities


@register_director('attempt2')
class AttemptDosDirector(Director):
    """Strategies based on a heat map of mine probabilities"""

    def act(self):
        total_mines_left = self.control.get_mines_left()
        all_cells = self.control.get_cells()

        systems = None
        next_systems = frozenset(find_systems(all_cells, maximum=total_mines_left))

        moves = []
        probabilities = []

        while systems != next_systems:
            logger.info('Simplifying systems')

            moves = []
            probabilities = []

            systems = frozenset(next_systems)
            next_systems = set()
            maximum = total_mines_left - sum(system.minimum for system in systems)

            for system in systems:
                system = system.simplify(maximum=maximum)
                next_systems.add(system)
                proposed_moves, remaining_probabilities = split_moves(system.groups)
                moves.extend(proposed_moves)
                probabilities.extend(remaining_probabilities)

            if moves:
                logger.info('Found moves...')
                break

        systems = next_systems
        logger.info('Finished simplifying')

        if moves:
            exec_moves(set(moves))

        else:
            assert probabilities

            # Display each system, for visual debugging purposes. And 'cause it
            # looks pretty, I guess.
            for system in systems:
                for cell in system.unrevealed:
                    cell.mark1()
                for cell in system.edges:
                    cell.mark2()

            probabilities = list(probabilities)
            probabilities.sort(key=lambda t: t[0])
            probability, cell = probabilities[0]
            exec_moves([
                ('click', cell, probability)
            ])
