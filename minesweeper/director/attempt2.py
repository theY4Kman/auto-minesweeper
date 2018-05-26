import logging
from typing import Iterable, Tuple, Set

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

    def find_visible_groups(self) -> Group:
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
            yield Group(remaining_unrevealed, self.control.get_mines_left())

    def simplify_groups(self, groups: Iterable[Group]) -> Set[Group]:
        clean = False
        graph = GroupGraph(groups)

        while not clean:
            clean = True

            for group in sorted(graph, key=len):
                contained_groups = graph.relatives_contained_by(group)

                if contained_groups:
                    graph.remove(group)
                    for contained in contained_groups:
                        graph.add(group - contained)
                    clean = False

        return set(graph)

    def flatten_groups(self, groups: Iterable[Group]) -> Tuple[float, Cell]:
        graph = GroupGraph(groups)
        for cell in graph.all_props():
            containers = graph.objects_containing(cell)
            yield max(group.probability for group in containers), cell

    def act(self):
        groups = set(self.find_visible_groups())
        groups = self.simplify_groups(groups)

        probabilities = tuple(self.flatten_groups(groups))
        assert probabilities, "No unrevealed cells left!"

        to_flag = tuple(c for probability, c in probabilities if probability == 1)
        to_reveal = tuple(c for probability, c in probabilities if probability == 0)

        if to_flag or to_reveal:
            for cell in to_flag:
                cell.right_click()
            for cell in to_reveal:
                cell.click()

        else:
            probabilities = tuple(sorted(probabilities, key=lambda t: t[0]))
            _, cell = probabilities[0]
            cell.click()
