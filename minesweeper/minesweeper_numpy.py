import re
from dataclasses import dataclass
from io import StringIO
from typing import Tuple

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
            numbers=np.zeros((height, width), dtype=np.uint8),
            mines=np.zeros((height, width), dtype=np.bool),
            reveals=np.zeros((height, width), dtype=np.bool),
            flags=np.zeros((height, width), dtype=np.bool),
        )

    def fill_mines(self, num_mines: int) -> None:
        # Create our mines
        flat_mines = board.mines.view().reshape(-1)
        flat_mines[:num_mines] = True
        np.random.shuffle(flat_mines)

        # Propagate numbers by convolution
        kernel = np.array([
            [1, 1, 1],
            [1, 0, 1],
            [1, 1, 1],
        ])
        convolve(board.mines, kernel, output=board.numbers, mode='constant', cval=0)

    def serialize(self) -> np.array:
        serialized = np.full_like(self.mines, '#', dtype=np.unicode_)
        for x, y in np.ndindex(*self.mines.shape):
            if not board.reveals[x, y]:
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

        return serialized

    def __str__(self) -> str:
        buf = StringIO()
        np.savetxt(buf, self.serialize(), fmt='%s', delimiter='')
        return buf.getvalue()

    def is_lost(self) -> bool:
        return self.exploded_mine is not None

    def click(self, x: int, y: int):
        if self.flags[x, y]:
            return

        self.reveals[x, y] = True

        if self.mines[x, y]:
            self.exploded_mine = x, y

        elif self.numbers[x, y] == 0:
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


if __name__ == '__main__':
    while True:
        board = Board.empty()
        board.fill_mines(150)

        while True:
            print(board)

            while True:
                coords = input('Coordinates: ')
                match = re.match(r'\s*(\d+)\s*,\s*(\d+)\s*', coords)
                if not match:
                    print('Please enter coordinates in "x,y" format')
                    continue

                print()
                break

            x, y = int(match.group(1)), int(match.group(2))
            board.click(x, y)

            if board.is_lost():
                print()
                print('YOU LOSE!')
                print()
                break
