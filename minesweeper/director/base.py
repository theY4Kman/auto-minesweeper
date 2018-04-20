"""
A director controls the game, seeing only what a player might see.
"""
import math
from itertools import starmap
from typing import Set, Iterable

from minesweeper.util import apply_method_filter


class BaseControl(object):
    """Middleman between directors and the Game"""

    def __init__(self):
        self._history = []

    def click(self, x, y):
        """Click the cell at grid x & y.

        This reveals any unflagged, unrevealed cell.

        This may not change the state of the game, depending on the state of
        the cell at x, y.
        """
        self._history.append(('click', (x, y)))

    def right_click(self, x, y):
        """Right-click the cell at grid x & y.

        This toggles the flag on any unrevealed cell.

        This may not change the state of the game, depending on the state of
        the cell at x, y.
        """
        self._history.append(('right_click', (x, y)))

    def middle_click(self, x, y):
        """Middle-click the cell at grid x & y

        This cascades any numbered/empty cell, if it has the proper number of
        flagged neighbors.

        This may not change the state of the game, depending on the state of
        the cell at x, y.
        """
        self._history.append(('middle_click', (x, y)))

    def mark(self, x, y, mark_num):
        """Mark a cell with an arbitrary color, for visualization

        This does not change the state of the game at all – it's purely to aid
        debugging.
        """
        # TODO: handle validation of mark_num
        self._history.append((f'mark{mark_num}', (x, y)))

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

    def get_history(self):
        """Return the full history of actions

        Returns a list of tuples in the form:

            ('click', (x, y))
            ('right_click', (x, y))
            ('middle_click', (x, y))
        """
        return self._history

    def get_mines_left(self):
        """Return the number of unflagged mines left on the board"""
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

    def __str__(self):
        return 'Cell(x={x}, y={y}, type={type})'.format(
            x=self.x,
            y=self.y,
            type=self.get_type_display(),
            self=self,
        )

    def __repr__(self):
        return '<{self}>'.format(self=self)

    def get_type_display(self):
        names = {
            self.TYPE_UNREVEALED: 'unrevealed',
            self.TYPE_FLAG: 'flag',
        }

        return names.get(self.type) or str(self.type)

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

    def is_on_border(self):
        width, height = self._control.get_board_size()
        return (
            (self.x == 0 or self.x == width -1) or
            (self.y == 0 or self.y == height - 1)
        )

    def click(self):
        return self._control.click(self.x, self.y)

    def right_click(self):
        return self._control.right_click(self.x, self.y)

    def middle_click(self):
        return self._control.middle_click(self.x, self.y)

    def mark1(self):
        return self._control.mark(self.x, self.y, 1)

    def mark2(self):
        return self._control.mark(self.x, self.y, 2)

    def mark3(self):
        return self._control.mark(self.x, self.y, 3)

    def get_neighbor_at(self, d_x, d_y):
        return self._control.get_cell(self.x + d_x, self.y + d_y)

    def _get_neighbours(self, vectors, **filters):
        """
        :rtype: set of Cell
        """
        neighbors = starmap(self.get_neighbor_at, vectors)
        neighbors = filter(None, neighbors)
        neighbors = apply_method_filter(neighbors, **filters)
        return set(neighbors)

    def get_neighbor_deltas(self):
        return (
            (-1, -1),
            (0, -1),
            (1, -1),
            (1, 0),
            (1, 1),
            (0, 1),
            (-1, 1),
            (-1, 0),
        )

    def get_cardinal_neighbor_deltas(self):
        return (
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 0),
        )

    def get_neighbors(self, **filters) -> Set['Cell']:
        return self._get_neighbours(self.get_neighbor_deltas(), **filters)

    def get_cardinal_neighbors(self, **filters) -> Set['Cell']:
        return self._get_neighbours(self.get_cardinal_neighbor_deltas(), **filters)

    def get_neighbor_across_from(self, cell: 'Cell') -> 'Cell':
        d_x, d_y = self.x - cell.x, self.y - cell.y
        if (d_x, d_y) in self.get_neighbor_deltas():
            return self.get_neighbor_at(d_x, d_y)

    def get_cardinal_neighbor_across_from(self, cell: 'Cell') -> 'Cell':
        d_x, d_y = self.x - cell.x, self.y - cell.y
        if (d_x, d_y) in self.get_cardinal_neighbor_deltas():
            return self.get_neighbor_at(d_x, d_y)

    def get_perpendicular_neighbors_from(self, cell: 'Cell') -> Iterable['Cell']:
        if self.x != cell.x and self.y != cell.y:
            return ()

        deltas = ()  # appeasing the type checker
        d_x, d_y = self.x - cell.x, self.y - cell.y

        if d_x:
            d_x /= d_x
            deltas = (
                (d_x, 1),
                (d_x, -1),
            )

        if d_y:
            d_y /= d_y
            deltas = (
                (d_y, 1),
                (d_y, -1),
            )

        return self._get_neighbours(deltas)

    def trace_to(self, cell: 'Cell', **filters):
        """Yield all neighbours under a straight line to cell"""
        slope_x, slope_y = self.x - cell.x, self.y - cell.y
        dist = math.sqrt(slope_x ** 2 + slope_y ** 2)
        if dist == 0:
            return

        unit_x, unit_y = slope_x / dist, slope_y / dist

        x, y = cell.x, cell.y
        traveled = 0
        encountered = set()
        while traveled < dist:
            x += unit_x
            y += unit_y

            traced = self._control.get_cell(math.floor(x), math.floor(y))
            if traced and traced not in encountered:
                encountered.add(traced)
                yield traced

            traveled += dist

    @property
    def num_flags_left(self):
        return self.number - len(self.get_neighbors(is_flagged=True))


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
