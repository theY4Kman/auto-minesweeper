import logging
from typing import Iterable, Tuple, Set, Optional

from minesweeper.datastructures import PropertyGraph
from minesweeper.director.base import Director, Cell

logger = logging.getLogger(__name__)


class Group:
    """A set of cells and the known number of mines among them"""

    def __init__(self, unrevealed_cells: Iterable[Cell], num_mines: int):
        self.cells = frozenset(unrevealed_cells)
        self.num_mines = num_mines

    def deconstruct(self):
        return self.cells, self.num_mines

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
        return Group(self.cells - other.cells, self.num_mines - other.num_mines)

    def __sub__(self, other: 'Group') -> 'Group':
        return self.difference(other)


class GroupGraph(PropertyGraph[Group, Cell]):
    def __init__(self, groups: Iterable[Group] = None):
        super().__init__(groups, lambda group: group.cells)


class AttemptDosDirector(Director):
    """Strategies based on a heat map of mine probabilities"""

    def find_visible_groups(self) -> Iterable[Group]:
        """Find groups by naively matching numbers to their unrevealed neighbours

        This method may return subsets or duplicates of other groups.
        """
        remaining_unrevealed = {
            cell
            for cell in self.control.get_cells()
            if cell.is_unrevealed()
        }

        for cell in self.control.get_cells():
            if not cell.is_number():
                continue

            unrevealed = cell.get_neighbors(is_unrevealed=True)
            if not unrevealed:
                continue

            yield Group(unrevealed, cell.num_flags_left)
            remaining_unrevealed.difference_update(unrevealed)

        if remaining_unrevealed:
            # XXX: this may not accurately represent the number of mines left in
            #      the unrevealed cells which don't touch a number.
            # Is there any more informed way to set this?
            # Does it matter, pragmatically?
            # Is there a way to refactor, such that the pragmatics match the semantics?
            yield Group(remaining_unrevealed, len(remaining_unrevealed) // 2)

    def simplify_groups(self, groups: Iterable[Group]) -> Optional[Set[Group]]:
        clean = False
        graph = GroupGraph(groups)

        while not clean:
            clean = True

            for group in sorted(graph, key=len):
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

        return set(graph)

    def flatten_groups(self, groups: Iterable[Group]) -> Iterable[Tuple[float, Cell]]:
        graph = GroupGraph(groups)
        for cell in graph.all_props():
            containers = graph.objects_containing(cell)
            yield max(group.probability for group in containers), cell

    def find_moves(self, probabilities: Iterable[Tuple[float, Cell]]
                   ) -> Iterable[Tuple[str, Cell]]:
        for probability, cell in probabilities:
            if probability == 1:
                yield 'right_click', cell
            elif probability == 0:
                yield 'click', cell

    def exec_moves(self, moves: Iterable[Tuple[str, Cell]]):
        for method_name, cell in moves:
            method = getattr(cell, method_name)
            method()

    def act(self):
        groups = self.simplify_groups(self.find_visible_groups())
        probabilities = list(self.flatten_groups(groups))
        moves = tuple(self.find_moves(probabilities))

        if moves:
            # Found moves with 100% confidence
            self.exec_moves(moves)

        else:
            assert probabilities
            probabilities.sort(key=lambda t: t[0])
            _, cell = probabilities[0]
            cell.click()
