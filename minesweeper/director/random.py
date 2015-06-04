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
