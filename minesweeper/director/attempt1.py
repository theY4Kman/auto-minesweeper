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

from random import SystemRandom
random = SystemRandom()

from minesweeper.director.random_director import RandomExpansionDirector


class AttemptUnoDirector(RandomExpansionDirector):
    def __init__(self, *args, **kwargs):
        super(AttemptUnoDirector, self).__init__(*args, **kwargs)

        # Cached state for each step
        self._cells = None
        self._numbered = None
        self._revealed = None

    def act(self):
        self._cells = self.control.get_cells()
        self._numbered = [c for c in self._cells if c.is_number()]
        self._revealed = [c for c in self._cells if c.is_revealed()]

        methods = (
            self.obvious,
            self.grouping,
            self.first_click,
            self.expand_cardinally,
            self.expand_randomly,
        )

        for meth in methods:
            if meth():
                break

    def obvious(self):
        for cell in self._numbered:
            neighbors = cell.get_neighbors()
            flagged = [c for c in neighbors if c.is_flagged()]
            unrevealed = [c for c in neighbors if c.is_unrevealed()]

            # If the number of unrevealed neighbours matches our number, flag!
            total_neighbours = len(flagged) + len(unrevealed)
            if unrevealed and total_neighbours == cell.number:
                for neighbor in unrevealed:
                    neighbor.right_click()
                return True

            # If the number of flagged neighbours matches our number and we
            # still have unrevealed neighbours, cascade!
            if unrevealed and len(flagged) == cell.number:
                cell.middle_click()
                return True

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
                        for cell in unshared:
                            cell.click()
                        return True
                    else:
                        necessary_diff = neighbor_necessary - necessary
                        if necessary_diff == len(unshared):
                            for cell in unshared:
                                cell.right_click()
                            return True

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
            cell.click()
            return True

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
            cell.click()
            return True

    def expand_randomly(self):
        # If no cardinal neighbor found, fall back to random expansion
        super(AttemptUnoDirector, self).act()
