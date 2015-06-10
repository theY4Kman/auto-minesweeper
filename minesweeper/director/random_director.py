from __future__ import absolute_import

from random import SystemRandom
random = SystemRandom()

from minesweeper.director.base import Director


class RandomDirector(Director):
    def act(self):
        cells = self.control.get_cells()
        unrevealed = [c for c in cells if c.is_unrevealed()]
        random.shuffle(unrevealed)
        choice = unrevealed.pop()
        choice.click()


class RandomExpansionDirector(RandomDirector):
    def click_random(self):
        super(RandomExpansionDirector, self).act()

    def act(self):
        cells = self.control.get_cells()
        revealed = [c for c in cells if c.is_revealed()]
        if not revealed:
            # It's our first turn, just choose something random
            self.click_random()
            return

        # Grab all unrevealed neighbours of revealed squares
        choices = set()
        for cell in revealed:
            neighbors = {c for c in cell.get_neighbors() if c.is_unrevealed()}
            choices.update(neighbors)

        choices = list(choices)
        selection = random.choice(choices)
        selection.click()
