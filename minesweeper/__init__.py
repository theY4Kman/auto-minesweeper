from minesweeper.director.attempt1 import AttemptUnoDirector
from minesweeper.game import Game


if __name__ == '__main__':
    game = Game()
    director = AttemptUnoDirector()
    game.set_director(director)
    game.run()
