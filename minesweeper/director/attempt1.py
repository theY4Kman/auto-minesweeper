from minesweeper.director.random import RandomExpansionDirector


class AttemptUnoDirector(RandomExpansionDirector):
    def act(self):
        cells = self.control.get_cells()
        numbered = [c for c in cells if c.is_number() and not c.is_empty()]

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

        # If no good choice found, fall back to random expansion
        super(AttemptUnoDirector, self).act()
