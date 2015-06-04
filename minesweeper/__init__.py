from minesweeper.game import Game
from minesweeper.director.random import RandomDirector


if __name__ == '__main__':
    game = Game()
    director = RandomDirector()
    game.set_director(director)
    game.run()
