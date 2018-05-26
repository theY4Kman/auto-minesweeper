from minesweeper.director.attempt1 import AttemptUnoDirector
from minesweeper.director.attempt2 import AttemptDosDirector
from minesweeper.game import Game
from minesweeper.main import main
from minesweeper.version import VERSION

__all__ = ['Game', 'AttemptUnoDirector', 'main']


__version__ = VERSION


if __name__ == '__main__':
    main()
