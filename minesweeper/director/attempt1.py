"""
TODO:
 - Grouping deductions amongst cells which don't touch:

    F|2|.       F|2|.
    F|3|.  =>   F|3|.
    .|#|#       .|#|#
    .|3|#       .|3|.

 - Grouping deductions requiring thought among several groups:

    O|#|O     O|#|F
    1|2|#  => 1|2|#
    .|1|O     .|1|O
"""

import logging
import math

from random import SystemRandom
random = SystemRandom()

from minesweeper.director.random_director import RandomExpansionDirector


logger = logging.getLogger(__name__)


class AttemptUnoDirector(RandomExpansionDirector):
    def __init__(self, *args, **kwargs):
        super(AttemptUnoDirector, self).__init__(*args, **kwargs)

        # Cached state for each step
        self._cells = None
        self._numbered = None
        self._revealed = None
        self._last_move = None

    def sort_by_last_move(self, cells):
        """Sort cells based on location near the last move"""
        return sorted(cells, key=lambda c: self.dist_to_last_move(c.x, c.y))

    def dist_to_last_move(self, x, y):
        if not self._last_move:
            return float('Inf')

        _, (l_x, l_y) = self._last_move
        return math.sqrt((x - l_x)**2 + (y - l_y)**2)

    def exec_moves(self, moves):
        """Execute moves in the form ('xyz_click', cell)"""
        for move in moves:
            self.exec_move(move)

    def exec_move(self, move):
        attr, cell = move
        getattr(cell, attr)()

    def act(self):
        # Sorting makes the director more visually appealing by having most
        # moves seem near each other.
        self._cells = self.sort_by_last_move(self.control.get_cells())
        self._numbered = [c for c in self._cells if c.is_number()]
        self._revealed = [c for c in self._cells if c.is_revealed()]

        history = self.control.get_history()
        if history:
            self._last_move = history[-1]

        confident = (
            self.obvious,
            self.grouping,
            self.first_click,
        )

        guess = (
            self.expand_cardinally,
            self.expand_randomly,
        )

        move_sets = filter(None, [meth() for meth in confident])
        best_set = None
        lowest_set_dist = float('Inf')
        for move_set in move_sets:
            lowest_dist = float('Inf')
            for _, cell in move_set:
                dist = self.dist_to_last_move(cell.x, cell.y)
                if dist < lowest_dist:
                    lowest_dist = dist

            if lowest_dist < lowest_set_dist:
                lowest_set_dist = lowest_dist
                best_set = move_set

        if not best_set and move_sets:
            best_set = random.choice(move_sets)

        if best_set:
            self.exec_moves(best_set)
            return

        for meth in guess:
            moves = meth()
            if moves:
                logger.debug('Executing meth %s moves %r',
                             meth.__name__, moves)
                self.exec_moves(moves)
                return

    def obvious(self):
        for cell in self._numbered:
            neighbors = cell.get_neighbors()
            flagged = [c for c in neighbors if c.is_flagged()]
            unrevealed = [c for c in neighbors if c.is_unrevealed()]

            # If the number of unrevealed neighbours matches our number, flag!
            total_neighbours = len(flagged) + len(unrevealed)
            if unrevealed and total_neighbours == cell.number:
                return [('right_click', c) for c in unrevealed]

            # If the number of flagged neighbours matches our number and we
            # still have unrevealed neighbours, cascade!
            if unrevealed and len(flagged) == cell.number:
                cell.middle_click()
                return [('middle_click', cell)]

    def grouping(self):
        # Deductive reasoning through grouping
        for cell in self._numbered:
            neighbors = cell.get_neighbors()
            numbered_neighbors = [c for c in neighbors if c.is_number()]

            flagged = [c for c in neighbors if c.is_flagged()]
            unrevealed = {c for c in neighbors if c.is_unrevealed()}
            necessary = cell.number - len(flagged)

            for neighbor in numbered_neighbors:
                neighbor_neighbors = neighbor.get_neighbors()
                neighbor_unrevealed = {c for c in neighbor_neighbors
                                       if c.is_unrevealed()}
                if (unrevealed.issubset(neighbor_unrevealed) and
                        unrevealed != neighbor_unrevealed):
                    neighbor_flagged = [c for c in neighbor_neighbors
                                        if c.is_flagged()]
                    neighbor_necessary = neighbor.number - len(neighbor_flagged)

                    unshared = neighbor_unrevealed - unrevealed
                    if necessary == neighbor_necessary:
                        return [('click', c) for c in unshared]
                    else:
                        necessary_diff = neighbor_necessary - necessary
                        if necessary_diff == len(unshared):
                            return [('right_click', c) for c in unshared]

    def first_click(self):
        if not self._revealed:
            # For our first turn, choose an edge
            w, h = self.control.get_board_size()
            edges = set()
            for y in xrange(h):
                edges.add((0, y))
                edges.add((w - 1, y))
            for x in xrange(w):
                edges.add((x, 0))
                edges.add((x, h - 1))
            edges = list(edges)
            coord = random.choice(edges)
            cell = self.control.get_cell(*coord)
            return [('click', cell)]

    def expand_cardinally(self):
        # If no other good choice, expand randomly in a cardinal direction
        # This gives a better chance of being able to use deductive reasoning
        # with groups next turn.
        cardinal_neighbors = set()
        scores = {}
        cardinal_deltas = (
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 0),
        )
        for cell in self._revealed:
            if not cell.number:
                continue

            neighbors = [cell.get_neighbor_at(d_x, d_y)
                         for d_x, d_y in cardinal_deltas]
            neighbors = [c for c in neighbors if c and c.is_unrevealed()]
            cardinal_neighbors.update(neighbors)

            all_neighbors = cell.get_neighbors()
            flagged = [c for c in all_neighbors if c.is_flagged()]
            unrevealed = [c for c in all_neighbors if c.is_unrevealed()]
            necessary = cell.number - len(flagged)
            score = float(necessary) / len(unrevealed) if unrevealed else 0

            for neighbor in neighbors:
                if score > scores.get(neighbor, -1):
                    scores[neighbor] = score

        if cardinal_neighbors:
            scored = [(score, cell) for cell, score in scores.iteritems()]
            scored.sort()
            _, cell = scored[0]
            return [('click', cell)]

    def expand_randomly(self):
        # If no cardinal neighbor found, fall back to random expansion
        choices = set()
        for cell in self._revealed:
            neighbors = {c for c in cell.get_neighbors() if c.is_unrevealed()}
            choices.update(neighbors)

        choices = list(choices)
        selection = random.choice(choices)
        return [('click', selection)]
