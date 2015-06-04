import os
import sys

from random import SystemRandom
random = SystemRandom()

import pygame
pygame.init()


ROOT_DIR = os.path.dirname(sys.argv[0])
IMAGE_DIR = os.path.join(ROOT_DIR, 'images')
FONT_DIR = os.path.join(ROOT_DIR, 'fonts')


FPS = 120
TICK = 1000 / FPS

# Board size in cells
BOARD_SIZE = 30, 16
BOARD_WIDTH, BOARD_HEIGHT = BOARD_SIZE

# Number of mines
MINES = 99

# Width/height of each cell
CELL_PX = 16

# Bezel border width
BORDER_PX = 3
BORDER_PX_0 = BORDER_PX - 1

SCOREBOARD_HEIGHT = 50

# Board margin
MARGIN_PX = 10

BG_COLOR = (220, 220, 220)


class Sprites(object):
    _sprite_names = {
        'empty',
        'flag',
        'flag_wrong',
        'mine_losing',
        'mine_unrevealed',
        'number1',
        'number2',
        'number3',
        'number4',
        'number5',
        'number6',
        'number7',
        'number8',
        'unrevealed',
    }

    def __init__(self):
        self._sprites = {}
        for name in self._sprite_names:
            image = pygame.image.load(os.path.join(IMAGE_DIR, name + '.png'))
            self._sprites[name] = image
            setattr(self, name, image)

    def __getitem__(self, item):
        return self._sprites[item]


def redraw_prop(attr):
    @property
    def prop(self):
        return getattr(self, attr)

    @prop.setter
    def prop(self, value):
        setattr(self, attr, value)
        self.should_redraw = True

    return prop


class Cell(object):
    def __init__(self, game, i_x, i_y, rect,
                 is_mine=False, is_flagged=False, is_revealed=False):
        self.game = game
        self.i_x = i_x
        self.i_y = i_y
        self.rect = rect

        self._is_mine = is_mine
        self._is_flagged = is_flagged
        self._is_revealed = is_revealed

        # Whether this mine was clicked to lose the game
        self._is_losing_mine = False
        # Whether the game is over
        self._is_game_over = False

        # Cached number for our cell
        self.number = None

        # Whether we need to do any drawing
        self.should_redraw = True

    is_mine = redraw_prop('_is_mine')
    is_losing_mine = redraw_prop('_is_losing_mine')
    is_flagged = redraw_prop('_is_flagged')
    is_revealed = redraw_prop('_is_revealed')
    is_game_over = redraw_prop('_is_game_over')

    def neighbors(self):
        return filter(None, map(lambda t: self._get_neighbour(*t), [
            (-1, -1),
            (0, -1),
            (1, -1),
            (1, 0),
            (1, 1),
            (0, 1),
            (-1, 1),
            (-1, 0),
        ]))

    def neighbor_mines(self):
        return [n for n in self.neighbors() if n.is_mine]

    def neighbor_friendlies(self):
        return [n for n in self.neighbors() if not n.is_mine]

    def neighbor_flags(self):
        return [n for n in self.neighbors() if n.is_flagged]

    def _get_neighbour(self, di_x, di_y):
        """dix and diy are grid indexes"""
        return self.game.board.get((self.i_x + di_x, self.i_y + di_y))

    def determine_number(self):
        if not self.is_mine:
            self.number = len(self.neighbor_mines())

    def draw(self):
        if self.should_redraw:
            self.should_redraw = False
            return self._draw()

    def _determine_sprite(self):
        if self.is_revealed:
            if self.is_mine:
                if self.is_losing_mine:
                    return 'mine_losing'
                else:
                    return 'mine'
            elif self.number:
                return 'number%d' % self.number
            else:
                return 'empty'
        else:
            if self.is_game_over and self.is_mine:
                return 'mine_unrevealed'
            elif self.is_flagged:
                if self.is_mine or not self.is_game_over:
                    return 'flag'
                else:
                    return 'flag_wrong'
            else:
                return 'unrevealed'

    def _draw(self):
        sprite = self._determine_sprite()
        if sprite:
            image = self.game.sprites[sprite]
            self.game.screen.blit(image, self.rect)
            return True

    def handle_click(self):
        if not self.is_revealed and not self.is_flagged:
            self.is_revealed = True
            self.game.on_cell_revealed(self)

            if self.is_mine:
                self.is_losing_mine = True
                self.game.lose()
            elif self.number == 0:
                self.cascade_empty(self)

    def handle_middleclick(self):
        if self.number is not None:
            self.cascade()

    def handle_rightclick(self):
        if not self.is_revealed:
            self.is_flagged = not self.is_flagged
            if self.is_flagged:
                self.game.on_cell_flagged(self)
            else:
                self.game.on_cell_unflagged(self)

    def cascade(self):
        """Reveal all unflagged neighbours if we have flagged the right amt"""
        should_cascade = len(self.neighbor_flags()) == self.number
        if should_cascade:
            self._cascade()

    def _cascade(self):
        to_reveal = [c for c in self.neighbors() if not (c.is_flagged or
                                                         c.is_revealed)]
        for cell in to_reveal:
            cell.handle_click()

    def cascade_empty(self, cell):
        """Reveal all neighbours of empty cells, recursively"""
        friendlies = cell.neighbor_friendlies()
        unrevealed = [c for c in friendlies if not (c.is_revealed or
                                                    c.is_flagged)]
        for c in unrevealed:
            c.is_revealed = True
            if c.number == 0:
                self.cascade_empty(c)


class Game(object):
    sprites = Sprites()

    def __init__(self):
        self.init_pygame()
        self.init_game()

    def init_pygame(self):
        self.halt = False
        self.screen = pygame.display.set_mode([
            BOARD_WIDTH * CELL_PX + MARGIN_PX * 2,
            BOARD_HEIGHT * CELL_PX + MARGIN_PX * 2 + SCOREBOARD_HEIGHT,
        ])
        self.screen.fill(BG_COLOR)
        self.clock = pygame.time.Clock()

        self.scoreboard_rect = pygame.Rect(MARGIN_PX, MARGIN_PX,
                                           100, SCOREBOARD_HEIGHT)

        font_path = os.path.join(FONT_DIR, 'VT323-Regular.ttf')
        self.scoreboard_font = pygame.font.Font(font_path, 36)

        pygame.display.set_caption('Minesweeper')

    def init_game(self):
        self.lost = False

        self.mines_left = MINES
        self._last_mines_left = None

        # Whether a square has been revealed
        self.has_revealed = False
        self.mousedown_cell = None

        self.board = {(i_x, i_y): Cell(self, i_x, i_y,
                                       pygame.Rect(x, y, CELL_PX, CELL_PX))
                      for i_x, x, i_y, y in self.grid()}
        self.choose_mines()
        self.determine_numbers()

    def grid(self):
        w = BOARD_WIDTH * CELL_PX
        h = BOARD_HEIGHT * CELL_PX

        for i_x, x in enumerate(xrange(MARGIN_PX, MARGIN_PX + w, CELL_PX)):
            for i_y, y in enumerate(xrange(MARGIN_PX + SCOREBOARD_HEIGHT,
                                           SCOREBOARD_HEIGHT + MARGIN_PX + h,
                                           CELL_PX)):
                yield i_x, x, i_y, y

    def choose_mines(self):
        possibilities = self.board.values()
        random.shuffle(possibilities)
        mines = possibilities[:MINES]
        for cell in mines:
            cell.is_mine = True

    def determine_numbers(self):
        for cell in self.board.itervalues():
            cell.determine_number()

    def get_cell_under_mouse(self, x, y):
        x, y = x - MARGIN_PX, y - MARGIN_PX - SCOREBOARD_HEIGHT
        i_x, i_y = int(x) / CELL_PX, int(y) / CELL_PX
        return self.board.get((i_x, i_y))

    def lose(self):
        self.lost = True
        for cell in self.board.itervalues():
            cell.is_game_over = True

    def on_cell_revealed(self, cell):
        self.has_revealed = True

    def on_cell_flagged(self, cell):
        self.mines_left -= 1

    def on_cell_unflagged(self, cell):
        self.mines_left += 1

    def clear_score(self):
        self.screen.fill((0, 0, 0), self.scoreboard_rect)

    def draw_score(self):
        self.clear_score()

        text = '%02d' % self.mines_left
        color = (0, 255, 0)
        scoreboard = self.scoreboard_font.render(text, 1, color)
        self.screen.blit(scoreboard, self.scoreboard_rect)

    def handle_click(self, button, cell):
        if button == 1:
            if not self.has_revealed and cell.is_mine:
                self.reconfigure_board(cell)
            cell.handle_click()
        if button == 2:
            cell.handle_middleclick()
        elif button == 3:
            cell.handle_rightclick()

    def run(self):
        self.halt = False
        self.mainloop()

    def mainloop(self):
        dirty_rects = []
        mousedown_cell = None
        mousedown_button = None

        while not self.halt:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.halt = True

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mousedown_cell = self.get_cell_under_mouse(*event.pos)
                    mousedown_button = event.button

                elif event.type == pygame.MOUSEBUTTONUP:
                    if mousedown_button == event.button:
                        mouseup_cell = self.get_cell_under_mouse(*event.pos)
                        if not self.lost and (mouseup_cell and
                                              mouseup_cell is mousedown_cell):
                            self.handle_click(event.button, mouseup_cell)

                        elif self.lost and mouseup_cell is None:
                            # The margin has been clicked, restart
                            self.init_game()

                    mousedown_cell = None
                    mousedown_button = None

            for cell in self.board.itervalues():
                if cell.draw():
                    dirty_rects.append(cell)

            if self._last_mines_left != self.mines_left:
                self.draw_score()
                dirty_rects.append(self.scoreboard_rect)

            if dirty_rects:
                pygame.display.update(dirty_rects)
                dirty_rects = []

            self.clock.tick(TICK)

        if self.halt:
            pygame.quit()

    def reconfigure_board(self, cell):
        """Moves a mine if it's the first cell clicked"""
        cells = self.board.values()
        random.shuffle(cells)
        while cells:
            possible_cell = cells.pop()
            if possible_cell is cell:
                continue
            if possible_cell.is_mine:
                continue

            possible_cell.is_mine = True
            cell.is_mine = False
            break
        self.determine_numbers()


if __name__ == '__main__':
    game = Game()
    game.run()
