from minesweeper.game import Game
from minesweeper.director.random import RandomExpansionDirector


if __name__ == '__main__':
    game = Game()
    director = RandomExpansionDirector()
    game.set_director(director)
    game.run()
