import logging
import random
from copy import copy
from itertools import chain
from typing import Iterable, Tuple, Union, Any

from minesweeper.datastructures import PropertyGraph
from minesweeper.director.base import Director, Cell

logger = logging.getLogger(__name__)


#XXX######################################################################################
import sys
logger.propagate = False
handler = logging.StreamHandler(sys.stdout)
handler.flush = sys.stdout.flush
logger.handlers.append(handler)
#XXX######################################################################################


class Group:
    """A set of cells and the known number of mines among them"""

    @classmethod
    def null(cls):
        return cls((), 0, 0)

    def __init__(self, cells: Iterable, lower_bound=0, upper_bound=None, sources=()):
        """
        :param cells: Cells in the group
        :param lower_bound: Minimum number of mines spread throughout the group
        :param upper_bound: Maximum number of mines that could be hiding in the group
        :param sources: A set of identifiers explaining where the information from
            the group came from. For debugging purposes.
        """
        self.cells = frozenset(cells)
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.sources = frozenset(sources)

    def __repr__(self):
        coords = [f'({c.x},{c.y})' for c in sorted(self.cells, key=lambda c: (c.x, c.y))]
        return f'G(min={self.lower_bound}, ' \
                 f'max={self.upper_bound}, ' \
                 f'cells|{len(self.cells)}|={{{" ".join(coords)}}})'

    def deconstruct(self):
        return self.cells, self.lower_bound, self.upper_bound

    def __hash__(self):
        return hash(self.deconstruct())

    def __eq__(self, other: 'Group'):
        assert isinstance(other, Group)
        return self.deconstruct() == other.deconstruct()

    def __len__(self):
        return len(self.cells)

    def __bool__(self):
        return len(self.cells) > 0

    def __sub__(self, other: 'Group') -> 'Group':
        cells = self.cells - other.cells
        upper_bound = min(
            len(cells),
            self.upper_bound - (other.lower_bound - len(other.cells - self.cells))
        )
        lower_bound = max(
            0,
            self.lower_bound - min(self.upper_bound, other.upper_bound)
        )

        #XXX######################################################################################
        #XXX######################################################################################
        if self.sources == {'board'} or True:
            result_divider = '-' * (max(len(repr(self)), len(repr(other))) + 3)
            result = Group(cells, lower_bound, upper_bound, sources=self.sources)
            logger.debug('   %r', self)
            logger.debug(' - %r', other)
            logger.debug(result_divider)
            logger.debug('   %r %.3f', result, result.probability)
            logger.debug('')
        #XXX######################################################################################
        #XXX######################################################################################
        #XXX######################################################################################

        return Group(cells, lower_bound, upper_bound, sources=self.sources)

    def __and__(self, other: 'Group') -> 'Group':
        cells = self.cells & other.cells
        upper_bound = min(
            len(cells),
            self.upper_bound,
            other.upper_bound,
        )
        lower_bound = max(
            0,
            self.lower_bound - len(self.cells - other.cells),
            other.lower_bound - len(other.cells - self.cells)
        )

        #XXX######################################################################################
        #XXX######################################################################################
        if self.sources == {'board'} or other.sources == {'board'} or True:
            result_divider = '-' * (max(len(repr(self)), len(repr(other))) + 3)
            result = Group(cells, lower_bound, upper_bound, sources=self.sources | other.sources)
            logger.debug('   %r', self)
            logger.debug(' & %r', other)
            logger.debug(result_divider)
            logger.debug('   %r %.3f', result, result.probability)
            logger.debug('')
        #XXX######################################################################################
        #XXX######################################################################################
        #XXX######################################################################################

        return Group(cells, lower_bound, upper_bound, sources=self.sources | other.sources)

    def combine(self, other: 'Group') -> Iterable['Group']:
        def combinations():
            #XXX######################################################################################
            #XXX######################################################################################
            result_divider = '-' * (max(len(repr(self)), len(repr(other))) + 3)
            logger.debug(result_divider + '\n')
            yield self - other
            yield self & other
            yield other - self
            logger.debug(result_divider + '\n')
            #XXX######################################################################################

        return tuple(group for group in combinations() if group)

    @property
    def probability(self):
        if self.lower_bound == self.upper_bound == 0:
            return 0
        elif self.lower_bound == self.upper_bound == len(self):
            return 1
        else:
            #XXX######################################################################################
            if not len(self):
                return float('NaN')
            #XXX######################################################################################
            return (self.lower_bound / len(self) + self.upper_bound / len(self)) / 2

    @property
    def is_solid(self):
        """Whether there's no wiggle room between our lower and upper bounds"""
        return self.lower_bound == self.upper_bound

    @property
    def is_confident(self):
        """Whether the group has enough info to flag or reveal cells"""
        return self.is_solid and (self.lower_bound == 0 or self.lower_bound == len(self))


class GroupGraph(PropertyGraph[Group, Cell]):
    """Relate groups by the cells they refer to"""

    def __init__(self, groups: Iterable[Group] = None):
        super().__init__(groups, lambda group: group.cells)


UNSET = object()


class System(frozenset):
    """A set of cells which are completely independent of other board cells"""

    __slots__ = ('unrevealed', 'edges', 'lower_bound', 'upper_bound', 'groups')

    def __new__(cls, unrevealed: Iterable[Cell], edges: Iterable[Cell], *args, **kwargs):
        return super().__new__(cls, chain(unrevealed, edges))

    def __init__(self,
                 unrevealed: Iterable[Cell], edges: Iterable[Cell],
                 lower_bound: int=None, upper_bound: int=None,
                 groups=()):
        self.unrevealed = frozenset(unrevealed)
        self.edges = frozenset(edges)
        self.lower_bound = 0 if lower_bound is None else lower_bound
        self.upper_bound = len(self.unrevealed) if upper_bound is None else upper_bound
        self.groups = frozenset(groups or ())
        super(System, self).__init__()

    def __copy__(self):
        return self.__class__(self.unrevealed, self.edges,
                              lower_bound=self.lower_bound, upper_bound=self.upper_bound,
                              groups=self.groups)

    def __hash__(self):
        return hash((frozenset(self), self.lower_bound, self.upper_bound, self.groups))

    @classmethod
    def trace(cls, start: Cell, upper_bound=None) -> 'System':
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

        system = cls(unrevealed, edges, upper_bound=upper_bound)
        system.groups = frozenset(cls.find_visible_groups(system, upper_bound))

        return system

    @staticmethod
    def find_visible_groups(cells, total_cells_left) -> Iterable[Group]:
        """Find groups by naively matching numbers to their unrevealed neighbours

        This method may return subsets or duplicates of other groups.
        """
        cells = tuple(cells)
        all_unrevealed = {cell for cell in cells if cell.is_unrevealed()}
        numbered = {cell for cell in cells if cell.is_number()}

        remaining_unrevealed = set(all_unrevealed)
        for cell in numbered:
            unrevealed = cell.get_neighbors(is_unrevealed=True)
            if not unrevealed:
                continue

            yield Group(unrevealed, cell.num_flags_left, cell.num_flags_left, sources={'number'})
            remaining_unrevealed.difference_update(unrevealed)

        # Since the process of determining the *actual* upper bound of the
        # remaining unrevealed cells not touching a number is NP-complete, here
        # we just yield a board-wide group with info from the total mines left,
        # and leave it to simplification to make it into anything useful.
        yield Group(all_unrevealed, 0, min(len(all_unrevealed), total_cells_left), sources={'board'})

    def simplify(self, upper_bound: int=None) -> 'System':
        """Return a more compact representation of the system, if possible
        """
        system = copy(self)
        if upper_bound is not None:
            system.upper_bound = upper_bound

        graph = GroupGraph(system.groups)
        clean = False

        while not clean:
            clean = True

            non_board_groups = (group for group in graph if group.sources != {'board'})
            groups: Iterable[Group] = sorted(non_board_groups, key=len, reverse=True)
            for group in groups:
                contained_groups = graph.relatives_of(group)

                if contained_groups:
                    contained_groups = sorted(contained_groups,
                                              key=lambda contained: len(contained.cells & group.cells),
                                              reverse=True)

                    # for contained in contained_groups:
                    contained = next(iter(contained_groups))
                    combined = group.combine(contained)
                    if any(g.is_confident and g not in graph for g in combined):
                        clean = False

                    if not group.is_confident:
                        graph.remove(group)
                    if not group.is_confident:
                        graph.remove(contained)
                    graph.update(combined)

        independents = {group
                        for group in graph.get_independent_objects()
                        if group.upper_bound < float('inf')}
        independent_mines = sum(independent.upper_bound for independent in independents)
        if independent_mines == system.upper_bound:
            other_groups = set(graph) - independents
            other_cells = {cell for group in other_groups for cell in group.cells}
            if other_cells:
                graph = GroupGraph(independents | {Group(other_cells, 0, 0)})

        if independents:
            system.lower_bound = sum(group.lower_bound for group in independents)

        system.groups = frozenset(graph)
        return system


def flatten_groups(groups: Iterable[Group]) -> Iterable[Tuple[float, Cell]]:
    """Determine probability of each cell using info from the passed groups
    """
    graph = GroupGraph(groups)
    for cell in sorted(graph.all_props(), key=lambda cell: (cell.x, cell.y)):
        containers = graph.objects_containing(cell)

        confident_groups = [group for group in containers if group.is_confident]
        if confident_groups:
            confident_group = confident_groups[0]
            probability = confident_group.probability
        else:
            probability = max(group.probability for group in containers)

        yield probability, cell


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


def find_systems(cells: Iterable[Cell], upper_bound: int=None) -> Iterable[System]:
    """Find all groups of cells separated from other groups
    """
    cells = {cell for cell in cells if cell.is_unrevealed()}

    while cells:
        system = System.trace(cells.pop(), upper_bound=upper_bound)
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


class AttemptDosDirector(Director):
    """Strategies based on a heat map of mine probabilities"""

    def act(self):
        total_mines_left = self.control.get_mines_left()
        all_cells = self.control.get_cells()

        systems = None
        next_systems = frozenset(find_systems(all_cells, upper_bound=total_mines_left))

        moves = []
        probabilities = []

        while systems != next_systems:
            logger.info('Simplifying systems')

            moves = []
            probabilities = []

            systems = frozenset(next_systems)
            next_systems = set()
            upper_bound = total_mines_left - sum(system.lower_bound for system in systems)

            for system in systems:
                system = system.simplify(upper_bound=upper_bound)
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
            logger.info('Choosing confident move')
            exec_moves(sorted(set(moves), key=lambda t: (t[1].x, t[1].y)))

        else:
            # Display each system, for visual debugging purposes. And 'cause it
            # looks pretty, I guess.
            for system in systems:
                for cell in system.unrevealed:
                    cell.mark1()
                for cell in system.edges:
                    cell.mark2()

            if probabilities:
                logger.info('Choosing random-ish move')

                probabilities = list(probabilities)
                probabilities.sort(key=lambda t: t[0])

                # Heuristic: below a certain probability, who cares?
                top_probability, _ = probabilities[0]
                probability_cutoff = max(0.2, top_probability)

                top_tier_cells = [cell
                                  for probability, cell in probabilities
                                  if probability <= probability_cutoff]
                cell = random.choice(top_tier_cells)
                exec_moves([
                    ('click', cell, 'random choice <= %.3f' % probability_cutoff)
                ])
