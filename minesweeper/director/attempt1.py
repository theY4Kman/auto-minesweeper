from random import SystemRandom
random = SystemRandom()

from minesweeper.director.random import RandomExpansionDirector


class AttemptUnoDirector(RandomExpansionDirector):
    def act(self):
        cells = self.control.get_cells()
        numbered = [c for c in cells if c.is_number()]

        for cell in numbered:
            neighbors = cell.get_neighbors()
            flagged = [c for c in neighbors if c.is_flagged()]
            unrevealed = [c for c in neighbors if c.is_unrevealed()]

            # If the number of unrevealed neighbours matches our number, flag!
            total_neighbours = len(flagged) + len(unrevealed)
            if unrevealed and total_neighbours == cell.number:
                for neighbor in unrevealed:
                    neighbor.right_click()
                return

            # If the number of flagged neighbours matches our number and we
            # still have unrevealed neighbours, cascade!
            if unrevealed and len(flagged) == cell.number:
                cell.middle_click()
                return

        # Deductive reasoning through grouping
        for cell in numbered:
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
                        return
                    else:
                        necessary_diff = neighbor_necessary - necessary
                        if necessary_diff == len(unshared):
                            for cell in unshared:
                                cell.right_click()
                            return

        revealed = [c for c in cells if c.is_revealed()]
        if not revealed:
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
            return

        # If no good choice found, fall back to random expansion
        super(AttemptUnoDirector, self).act()
