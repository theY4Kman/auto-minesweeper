import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Tuple, Generator

import arcade
import numpy as np
from scipy.ndimage import convolve, binary_dilation


cell_type = np.dtype([
    ('x', np.uint8),
    ('y', np.uint8),
    ('type', np.int8),
    ('is_revealed', np.bool),
    ('is_flagged', np.bool),
])

TYPE_MINE = -1
TYPE_EMPTY = 0


@dataclass
class Board:
    mines: np.array
    numbers: np.array
    reveals: np.array
    flags: np.array
    exploded_mine: Tuple[int, int] = None

    @classmethod
    def empty(cls, width: int = 60, height: int = 30) -> 'Board':
        return Board(
            reveals=np.zeros((width, height), dtype=np.bool),
            flags=np.zeros((width, height), dtype=np.bool),
            mines=np.zeros((width, height), dtype=np.bool),
            numbers=np.zeros((width, height), dtype=np.uint8),
        )

    def fill_mines(self, num_mines: int) -> None:
        # Create our mines
        flat_mines = self.mines.view().reshape(-1)
        flat_mines[:num_mines] = True
        np.random.shuffle(flat_mines)

        # Propagate numbers by convolution
        kernel = np.array([
            [1, 1, 1],
            [1, 0, 1],
            [1, 1, 1],
        ])
        convolve(self.mines, kernel, output=self.numbers, mode='constant', cval=0)

    def serialize(self) -> np.array:
        serialized = np.full_like(self.mines, '#', dtype=np.unicode_)
        for x, y in np.ndindex(*self.mines.shape):
            if not self.reveals[x, y]:
                continue

            if self.exploded_mine == (x, y):
                serialized[x, y] = '*'

            if self.flags[x, y]:
                serialized[x, y] = 'F'

            elif self.mines[x, y]:
                serialized[x, y] = 'O'

            else:
                number = self.numbers[x, y]
                if number == TYPE_EMPTY:
                    serialized[x, y] = ' '
                else:
                    serialized[x, y] = str(number)

        return serialized.T

    def __str__(self) -> str:
        buf = StringIO()
        np.savetxt(buf, self.serialize(), fmt='%s', delimiter='')
        return buf.getvalue()

    def enumerate_cells(self) -> Generator[Tuple[int, int, bool, bool, bool, int], None, None]:
        for x, y in np.ndindex(*self.mines.shape):
            yield x, y, self.reveals[x, y], self.flags[x, y], self.mines[x, y], self.numbers[x, y]

    def is_lost(self) -> bool:
        return self.exploded_mine is not None

    def click(self, x: int, y: int):
        if self.flags[x, y] or self.reveals[x, y]:
            return

        self.reveals[x, y] = True

        if self.mines[x, y]:
            self.exploded_mine = x, y

        elif self.numbers[x, y] == 0:
            self._cascade_empty(x, y)

    def middle_click(self, x: int, y: int):
        if self.flags[x, y] or not self.reveals[x, y]:
            return

        self.click(x, y)

    def right_click(self, x: int, y: int):
        self.flags[x, y] = not self.flags[x, y]

    def _cascade_empty(self, x: int, y: int):
        fill = np.zeros(self.numbers.shape, dtype=np.bool)
        fill[x, y] = True

        neighbors = np.array([
            [1, 1, 1],
            [1, 0, 1],
            [1, 1, 1],
        ])

        # First, fill our mask to all neighbouring 0's
        fill = binary_dilation(fill,
                               mask=np.logical_not(self.numbers),
                               structure=neighbors,
                               iterations=100)

        # Then, expand to include any numbers (i.e. non-mines) on our border,
        # and apply to our reveals
        binary_dilation(fill,
                        mask=~self.mines,
                        structure=neighbors,
                        output=self.reveals)


class Game(arcade.Window):

    # Width/height of each cell
    CELL_PX = 16

    def __init__(self,
                 width: int = 60,
                 height: int = 30,
                 num_mines: int = 99,
                 ):
        self.board_width = width
        self.board_height = height
        self.num_mines = num_mines

        super().__init__(
            width=self.board_width * self.CELL_PX,
            height=self.board_height * self.CELL_PX,
            title='Minesweeper',
        )

        self.board = Board.empty(
            width=self.board_width,
            height=self.board_height,
        )
        self.restart()

        self._sprite_dir = Path(__file__).parent / 'images'
        self.cell_list = None

        # arcade.set_background_color(arcade.color.RED)
        self.recreate_grid()

    def restart(self):
        self.board.fill_mines(self.num_mines)

    def recreate_grid(self):
        try:
            self._recreate_grid()
        except Exception as e:
            print(e)
            raise

    def _recreate_grid(self):
        self.cell_list = arcade.SpriteList()

        #XXX######################################################################################
        #XXX######################################################################################
        print()
        print(self.board)
        print()
        print(len(tuple(self.board.enumerate_cells())))
        print()
        #XXX######################################################################################
        #XXX######################################################################################

        is_lost = self.board.is_lost()
        for x, y, is_revealed, is_flagged, is_mine, number in self.board.enumerate_cells():
            if is_revealed:
                if is_mine:
                    if self.board.exploded_mine == (x, y):
                        sprite = 'mine_losing'
                    else:
                        sprite = 'mine'
                elif number:
                    sprite = f'number{number}'
                else:
                    sprite = 'empty'
            else:
                if is_flagged:
                    if is_mine or not is_lost:
                        sprite = 'flag'
                    else:
                        sprite = 'flag_wrong'
                elif is_lost and is_mine:
                    sprite = 'mine_unrevealed'
                else:
                    sprite = 'unrevealed'

            cell = arcade.Sprite(self._sprite_dir / f'{sprite}.png')
            cell.left = x * self.CELL_PX
            cell.top = (y + 1) * self.CELL_PX

            self.cell_list.append(cell)

        print(len(self.board.mines[self.board.mines == True]))

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        row = int(y // self.CELL_PX)
        col = int(x // self.CELL_PX)

        if button == arcade.MOUSE_BUTTON_LEFT:
            self.board.click(col, row)
        elif button == arcade.MOUSE_BUTTON_MIDDLE:
            self.board.middle_click(col, row)
        elif button == arcade.MOUSE_BUTTON_RIGHT:
            self.board.right_click(col, row)

        self.recreate_grid()

    def on_draw(self):
        arcade.start_render()
        self.cell_list.draw()


if __name__ == '__main__':
    game = Game(num_mines=250)
    arcade.run()
