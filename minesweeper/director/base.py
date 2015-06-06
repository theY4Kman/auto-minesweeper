"""
A director controls the game, seeing only what a player might see.
"""
from itertools import starmap


class BaseControl(object):
    """Middleman between directors and the Game"""

    def click(self, x, y):
        """Click the cell at grid x & y.

        This reveals any unflagged, unrevealed cell.

        This may not change the state of the game, depending on the state of
        the cell at x, y.
        """
        raise NotImplementedError

    def right_click(self, x, y):
        """Right-click the cell at grid x & y.

        This toggles the flag on any unrevealed cell.

        This may not change the state of the game, depending on the state of
        the cell at x, y.
        """
        raise NotImplementedError

    def middle_click(self, x, y):
        """Middle-click the cell at grid x & y

        This cascades any numbered/empty cell, if it has the proper number of
        flagged neighbors.

        This may not change the state of the game, depending on the state of
        the cell at x, y.
        """
        raise NotImplementedError

    def get_cell(self, x, y):
        """Get the Cell at grid x, y coords. Return None if out-of-bounds"""
        raise NotImplementedError

    def get_cells(self):
        """Return all cells, in (y, x) ascending order

        :rtype: list of Cell
        """
        raise NotImplementedError

    def get_board_size(self):
        """Return size of grid"""
        raise NotImplementedError

    def reset_cache(self):
        pass


class Cell(object):
    TYPE_NUMBER0 = 0
    TYPE_NUMBER1 = 1
    TYPE_NUMBER2 = 2
    TYPE_NUMBER3 = 3
    TYPE_NUMBER4 = 4
    TYPE_NUMBER5 = 5
    TYPE_NUMBER6 = 6
    TYPE_NUMBER7 = 7
    TYPE_NUMBER8 = 8
    TYPE_UNREVEALED = 9
    TYPE_FLAG = 10

    def __init__(self, control, x, y, type_):
        self._control = control

        self.x = x
        self.y = y
        self.type = type_

    @property
    def number(self):
        return self.type if self.is_number() else None

    def is_flagged(self):
        return self.type == Cell.TYPE_FLAG

    def is_number(self):
        # Though 0 is still a number, we never care about it like other nums
        return self.type <= Cell.TYPE_NUMBER8 and not self.is_empty()

    def is_empty(self):
        return self.type == Cell.TYPE_NUMBER0

    def is_unrevealed(self):
        return self.type == Cell.TYPE_UNREVEALED

    def is_revealed(self):
        return not self.is_unrevealed()

    def click(self):
        return self._control.click(self.x, self.y)

    def right_click(self):
        return self._control.right_click(self.x, self.y)

    def middle_click(self):
        return self._control.middle_click(self.x, self.y)

    def get_neighbor_at(self, d_x, d_y):
        return self._control.get_cell(self.x + d_x, self.y + d_y)

    def get_neighbors(self):
        """
        :rtype: list of Cell
        """
        all_neighbors = starmap(self.get_neighbor_at, (
            (-1, -1),
            (0, -1),
            (1, -1),
            (1, 0),
            (1, 1),
            (0, 1),
            (-1, 1),
            (-1, 0),
        ))
        return filter(None, all_neighbors)


class Director(object):
    def __init__(self, control=None):
        """
        :type control: BaseControl
        """
        self.control = control

    def set_control(self, control):
        self.control = control

    def act(self):
        """Called by the game. Act on the board here."""
