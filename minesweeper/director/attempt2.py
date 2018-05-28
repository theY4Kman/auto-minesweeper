import logging
import operator
from functools import reduce
from itertools import chain
from typing import Iterable, Tuple, Set, Optional, Union

from minesweeper.datastructures import PropertyGraph
from minesweeper.director.base import Director, Cell

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
        return self.deconstruct() == other.deconstruct()

    def __len__(self):
        return len(self.cells)

    @property
    def probability(self):
        return self.num_mines / len(self)

    def difference(self, other: 'Group') -> 'Group':
        assert other.cells.issubset(self.cells)
        return Group(self.num_mines - other.num_mines, self.cells - other.cells)

    def __sub__(self, other: 'Group') -> 'Group':
        return self.difference(other)


class GroupGraph(PropertyGraph[Group, Cell]):
    """Relate groups by the cells they refer to"""

    def __init__(self, groups: Iterable[Group] = None):
        super().__init__(groups, lambda group: group.cells)


class System(frozenset):
    """A set of cells which are completely independent of other board cells"""

    def __new__(cls, unrevealed: Iterable[Cell], edges: Iterable[Cell]):
        return super().__new__(cls, chain(unrevealed, edges))

    def __init__(self, unrevealed: Iterable[Cell], edges: Iterable[Cell]):
        self.unrevealed = frozenset(unrevealed)
        self.edges = frozenset(edges)
        super(System, self).__init__()

    @classmethod
    def trace(cls, start: Cell) -> 'System':
        """Find all cells of a system, given an unrevealed cell"""
        assert start.is_unrevealed()  # sanity check

        walked = set()
        unrevealed = set()
        edges = set()

        def fill(cursor: Cell):
            if cursor in walked:
                return

            walked.add(cursor)
            queue = set()

            if cursor.is_number():
                edges.add(cursor)
                queue |= cursor.get_neighbors(is_unrevealed=True)

            if cursor.is_unrevealed():
                unrevealed.add(cursor)
                queue |= cursor.get_neighbors(is_number=True)
                queue |= cursor.get_neighbors(is_unrevealed=True)

            for neighbor in queue:
                fill(neighbor)

        fill(start)
        return System(unrevealed, edges)


def find_visible_groups(cells) -> Iterable[Group]:
    """Find groups by naively matching numbers to their unrevealed neighbours

    This method may return subsets or duplicates of other groups.
    """
    remaining_unrevealed = {cell for cell in cells if cell.is_unrevealed()}

    for cell in cells:
        if not cell.is_number():
            continue

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


def simplify_groups(groups: Iterable[Group], total_mines_left: int) -> Optional[Set[Group]]:
    """Return a more compact representation of groups, if possible
    """
    clean = False
    graph = GroupGraph(groups)

    while not clean:
        clean = True

        groups: Iterable[Group] = sorted(graph, key=len)
        for group in groups:
            contained_groups = graph.relatives_contained_by(group)

            if contained_groups:
                clean = False
                graph.remove(group)

                for contained in contained_groups:
                    split_group = group - contained
                    if split_group.num_mines >= 0:
                        graph.add(split_group)
                    else:
                        # The groups passed are untrue – they don't jive with each other
                        return None

    useful_groups = (group.cells for group in groups if group.num_mines < float('Inf'))
    common = reduce(operator.and_, useful_groups, frozenset())
    if len(common) == total_mines_left:
        all = reduce(operator.or_, (group.cells for group in graph))
        return {Group(1, common), Group(0, all - common)}

    return set(graph)


def flatten_groups(groups: Iterable[Group]) -> Iterable[Tuple[float, Cell]]:
    """Determine probability of each cell using info from the passed groups
    """
    graph = GroupGraph(groups)
    for cell in graph.all_props():
        containers = graph.objects_containing(cell)
        yield max(group.probability for group in containers), cell


def exec_moves(moves: Iterable[Tuple[str, Cell]]):
    """Execute a list of moves
    """
    for method_name, cell in moves:
        method = getattr(cell, method_name)
        method()


def find_systems(cells: Iterable[Cell]) -> Iterable[System]:
    """Find all groups of cells separated from other groups
    """
    cells = {cell for cell in cells if cell.is_unrevealed()}

    while cells:
        system = System.trace(cells.pop())
        yield system
        cells -= system.unrevealed


class AttemptDosDirector(Director):
    """Strategies based on a heat map of mine probabilities"""

    def act(self):
        all_cells = self.control.get_cells()
        systems = tuple(find_systems(all_cells))

        moves = []
        probabilities = []

        for system in systems:
            groups = tuple(find_visible_groups(system))
            groups = simplify_groups(groups, self.control.get_mines_left())
            for probability, cell in flatten_groups(groups):
                if probability == 1:
                    moves.append(('right_click', cell))
                elif probability == 0:
                    moves.append(('click', cell))
                else:
                    probabilities.append((probability, cell))

        if moves:
            exec_moves(moves)

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
            cell.click()
            logger.debug('Could not find a confident move. '
                         'Clicking %r with probability %0.4f', cell, probability)
