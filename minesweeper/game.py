import os
from datetime import datetime

from random import SystemRandom
random = SystemRandom()

import pygame
pygame.init()

from minesweeper.director.base import BaseControl, Cell as DirectorCell


ROOT_DIR = os.path.dirname(__file__)
IMAGE_DIR = os.path.join(ROOT_DIR, 'images')
FONT_DIR = os.path.join(ROOT_DIR, 'fonts')

SAVE_DIR = os.path.join(ROOT_DIR, 'saved_games')
SAVE_WIN_DIR = os.path.join(SAVE_DIR, 'wins')
SAVE_LOSS_DIR = os.path.join(SAVE_DIR, 'losses')
SAVE_SCENARIOS_DIR = os.path.join(SAVE_DIR, 'scenarios')


for d in SAVE_WIN_DIR, SAVE_LOSS_DIR, SAVE_SCENARIOS_DIR:
    try:
        os.makedirs(d)
    except OSError:
        pass


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

# Number of frames to skip in between director actions
DIRECTOR_SKIP_FRAMES = 1


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

        for name, color in (
                ('left_click', (255, 0, 0)),
                ('middle_click', (0, 255, 0)),
                ('right_click', (0, 0, 255)),
        ):
            surface = pygame.Surface((CELL_PX, CELL_PX))
            surface.set_alpha(128)
            surface.fill(color)
            self[name] = surface

    def __getitem__(self, item):
        return self._sprites[item]

    def __setitem__(self, key, value):
        self._sprites[key] = value
        setattr(self, key, value)


def redraw_prop(attr):
    @property
    def prop(self):
        return getattr(self, attr)

    @prop.setter
    def prop(self, value):
        setattr(self, attr, value)
        self.mark_dirty()

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

    def serialize(self):
        if self.is_mine:
            if self.is_losing_mine:
                return '*'
            elif self.is_flagged:
                return 'F'
            else:
                return 'O'
        elif self.is_flagged:
            return 'f'
        elif self.is_revealed:
            return '.'
        else:
            return '#'

    def deserialize(self, c):
        if c in '*FO':
            self.is_mine = True
            if c == '*':
                self.is_losing_mine = True
            elif c == 'F':
                self.is_flagged = True
        elif c == 'f':
            self.is_flagged = True
        elif c == '.':
            self.is_revealed = True
        else:
            self.is_revealed = False

    def mark_dirty(self):
        """Mark the cell for drawing next frame"""
        self.should_redraw = True

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
            if self.is_flagged:
                if self.is_mine or not self.is_game_over:
                    return 'flag'
                else:
                    return 'flag_wrong'
            elif self.is_game_over and self.is_mine:
                return 'mine_unrevealed'
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

    def handle_middle_click(self):
        if self.number is not None:
            self.cascade()

    def handle_right_click(self):
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


class GameControl(BaseControl):
    def __init__(self, game):
        self._game = game
        self._cells = None
        self._cell_map = None

    def reset_cache(self):
        """Used by the Game to reset cache, causing cells to be recomputed"""
        self._cells = None
        self._cell_map = None

    def _get_cell_err(self, x, y):
        cell = self._get_raw_cell(x, y)
        if cell is None:
            raise IndexError('No cell at (%d, %d)' % (x, y))
        return cell

    def _get_raw_cell(self, x, y):
        return self._game.board.get((x, y))

    def get_cell(self, x, y):
        return self._cell_map.get((x, y))

    def _convert_cell(self, raw_cell):
        sprite = raw_cell._determine_sprite()
        if sprite.startswith('number'):
            type_ = raw_cell.number
        else:
            type_ = {
                'empty': DirectorCell.TYPE_NUMBER0,
                'flag': DirectorCell.TYPE_FLAG,
                'unrevealed': DirectorCell.TYPE_UNREVEALED,
            }.get(sprite)
        return DirectorCell(self, raw_cell.i_x, raw_cell.i_y, type_)

    def get_cells(self):
        if self._cells is None:
            cells = map(self._convert_cell, self._game.board.itervalues())
            cells.sort(key=lambda c: (c.x, c.y))
            self._cells = cells
            self._cell_map = {(c.x, c.y): c for c  in cells}
        return self._cells

    def click(self, x, y):
        cell = self._get_cell_err(x, y)
        return self._game.handle_click(1, cell)

    def right_click(self, x, y):
        cell = self._get_cell_err(x, y)
        return self._game.handle_click(3, cell)

    def middle_click(self, x, y):
        cell = self._get_cell_err(x, y)
        return self._game.handle_click(2, cell)

    def get_board_size(self):
        return BOARD_SIZE


class QueuedControl(BaseControl):
    """Queues actions to be performed later, allows marking of actions"""

    def __init__(self, control):
        """
        :type control: BaseControl
        """
        self._control = control
        self._queue = []

    def reset_cache(self):
        self._control.reset_cache()

    def get_cell(self, x, y):
        cell = self._control.get_cell(x, y)
        if cell:
            cell._control = self
        return cell

    def get_cells(self):
        cells = self._control.get_cells()
        for cell in cells:
            cell._control = self
        return cells

    def click(self, x, y):
        self._queue.append((1, x, y, lambda: self._control.click(x, y)))

    def right_click(self, x, y):
        self._queue.append((3, x, y, lambda: self._control.right_click(x, y)))

    def middle_click(self, x, y):
        self._queue.append((2, x, y, lambda: self._control.middle_click(x, y)))

    def get_board_size(self):
        return self._control.get_board_size()

    def exec_queue(self):
        queue = self._queue[::-1]
        try:
            while queue:
                _, _, _, func = queue.pop()
                func()
        finally:
            self._queue = queue[::-1]

    def clear_queue(self):
        self._queue = []

    def get_actions(self):
        for button, x, y, _ in self._queue:
            yield button, x, y


class Game(object):
    sprites = Sprites()

    director_buttons = {
        1: sprites.left_click,
        2: sprites.middle_click,
        3: sprites.right_click,
    }

    def __init__(self, tick=None):
        self.tick = tick or TICK

        # Whether to clear all neighbours of the first clicked cell (win7), or
        # just clear the cell (winXP)
        self.clear_neighbors_of_first_click = True

        # Declarations
        self.director = None
        self.director_control = None
        self.director_skip_frames = None
        self.director_act_at = None
        self.director_cell_redraw = None

        self.frame = None
        self.halt = None
        self.screen = None
        self.clock = None
        self.scoreboard_rect = None
        self.scoreboard_font = None

        self.lost = None
        self.won = None
        self.in_play = None
        self.mines_left = None
        self._last_mines_left = None
        self.has_revealed = None
        self.mousedown_cell = None
        self.board = None

        # Initializations
        self.init_pygame()
        self.init_game()

    def init_pygame(self):
        self.frame = 0
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
        self.width = BOARD_WIDTH
        self.height = BOARD_HEIGHT

        self.lost = self.won = False
        self.in_play = True
        self.director_skip_frames = DIRECTOR_SKIP_FRAMES
        self.director_act_at = self.frame + self.director_skip_frames
        self.director_cell_redraw = []

        if self.director_control:
            self.director_control.clear_queue()

        self.mines_left = MINES
        self._last_mines_left = None

        # Whether a square has been revealed
        self.has_revealed = False

        self.board = self._generate_board()
        self.choose_mines()
        self.determine_numbers()

    def _generate_board(self, c_w=None, c_h=None):
        return {(i_x, i_y): Cell(self, i_x, i_y,
                                 pygame.Rect(x, y, CELL_PX, CELL_PX))
                for i_x, x, i_y, y in self.grid(c_w, c_h)}

    def serialize(self):
        """Serialize the board state to a string.

        The output will look like the following:

            ##.......
            ###O#O#OO
            ..OO.O.O.
            ..Ff..*..

        Legend:

            O (letter oh) - mine, unrevealed
            # (hash) - unrevealed cell, not containing a mine
            . (period) - revealed cell, not containing a mine
            F (uppercase F) - flagged cell, containing a mine
            f (lowercase f) - flagged cell, not containing a mine
            * (asterisk) - revealed mine (this cell lost the game). The
                presence of this means the game has been lost.
        """
        chars = []
        last_y = None
        for i_x, _, i_y, _ in self.grid():
            if last_y is not None and i_y != last_y:
                chars.append('\n')
            cell = self.board[i_x, i_y]
            chars.append(cell.serialize())
            last_y = i_y
        return ''.join(chars)

    def save_fp(self, fp):
        """Serialize board state to a file-like object"""
        fp.write(self.serialize())

    def save(self, path, overwrite=False):
        if os.path.isfile(path) and not overwrite:
            raise OSError('%r exists, will not overwrite' % path)

        with open(path, 'w') as fp:
            self.save_fp(fp)

    def _format_filename(self, index=None, prefix='saved_', suffix='.txt'):
        date = datetime.now().strftime('%Y-%m-%d_%H-%M')
        parts = [prefix, date]
        if index is not None:
            parts.append('_%s' % index)
        parts.append(suffix)
        return ''.join(parts)

    def generate_filename(self, directory=None):
        path = filename = self._format_filename()
        if directory and os.path.isdir(directory):
            index = 1
            while True:
                path = os.path.join(directory, filename)
                if not os.path.exists(path):
                    break
                filename = self._format_filename(index=index)
                index += 1
        return path

    def load(self, path, unrevealed=False):
        with open(path, 'r') as fp:
            self.load_fp(fp, unrevealed=unrevealed)

    def load_fp(self, fp, unrevealed=False):
        s = fp.read().strip()
        self.deserialize(s, unrevealed=unrevealed)

    def deserialize(self, s, unrevealed=False):
        """Load in the specific board state

        :param unrevealed: only load flags; don't reveal or flag any cells
        """
        lines = s.split('\n')
        h = len(lines)
        w = len(lines[0])
        assert all(len(l) == w for l in lines)

        self.width = w
        self.height = h

        self.board = self._generate_board(w, h)
        for y, row in enumerate(lines):
            for x, c in enumerate(row):
                cell = self.board[(x, y)]
                cell.deserialize(c)

                if unrevealed:
                    cell.is_revealed = False
                    cell.is_losing_mine = False
                    cell.is_flagged = False
                else:
                    if cell.is_losing_mine:
                        self.won = False
                        self.lost = True
                        self.in_play = False
                        self._set_game_over()
                    if cell.is_revealed:
                        self.has_revealed = True

        self.determine_numbers()

    def grid(self, c_w=None, c_h=None):
        c_w = c_w or self.width
        c_h = c_h or self.height
        return self._grid(c_w, c_h)

    def _grid(self, c_w, c_h):
        w = c_w * CELL_PX
        h = c_h * CELL_PX

        for i_y, y in enumerate(xrange(MARGIN_PX + SCOREBOARD_HEIGHT,
                                       SCOREBOARD_HEIGHT + MARGIN_PX + h,
                                       CELL_PX)):
            for i_x, x in enumerate(xrange(MARGIN_PX, MARGIN_PX + w, CELL_PX)):
                yield i_x, x, i_y, y

    def choose_mines(self):
        possibilities = self.board.values()
        random.shuffle(possibilities)
        mines = possibilities[:MINES]
        for cell in mines:
            cell.is_mine = True

    def set_director(self, director):
        self.director = director
        self.director_control = QueuedControl(GameControl(self))
        self.director.set_control(self.director_control)

    def determine_numbers(self):
        for cell in self.board.itervalues():
            cell.determine_number()

    def get_cell_under_mouse(self, x, y):
        x, y = x - MARGIN_PX, y - MARGIN_PX - SCOREBOARD_HEIGHT
        i_x, i_y = int(x) / CELL_PX, int(y) / CELL_PX
        return self.board.get((i_x, i_y))

    def _set_game_over(self):
        for cell in self.board.itervalues():
            cell.is_game_over = True

    def lose(self):
        self.lost = True
        self.in_play = False
        self._set_game_over()

        self.save(self.generate_filename(SAVE_LOSS_DIR))

    def win(self):
        self.won = True
        self.in_play = False

        self.save(self.generate_filename(SAVE_WIN_DIR))

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

        if self.won:
            text = 'WIN!!!'
        elif self.lost:
            text = 'LOSE'
        else:
            text = '%02d' % self.mines_left

        color = (0, 255, 0)
        scoreboard = self.scoreboard_font.render(text, 1, color)
        self.screen.blit(scoreboard, self.scoreboard_rect)

    def draw_director_actions(self):
        dirty = []
        for button, x, y in self.director_control.get_actions():
            cell = self.board.get((x, y))
            if cell:
                surface = self.director_buttons[button]
                self.screen.blit(surface, cell.rect)
                dirty.append(cell.rect)

                # Mark cell for redraw after action occurs
                # This is necessary for cells whose clicking does not actually
                # change state (like a number)
                self.director_cell_redraw.append(cell)
        return dirty

    def redraw_cells(self, cells):
        for cell in cells:
            cell.mark_dirty()

    def handle_click(self, button, cell):
        if button == 1:
            if not self.has_revealed:
                self.reconfigure_board(cell)
            cell.handle_click()
        if button == 2:
            cell.handle_middle_click()
        elif button == 3:
            cell.handle_right_click()

    def run(self):
        self.halt = False
        self.mainloop()

    def mainloop(self):
        dirty_rects = []
        mousedown_cell = None
        mousedown_button = None
        director_redraw_cells = []

        while not self.halt:
            director_acted = False
            self.frame += 1

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.halt = True

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mousedown_cell = self.get_cell_under_mouse(*event.pos)
                    mousedown_button = event.button

                elif event.type == pygame.MOUSEBUTTONUP:
                    if mousedown_button == event.button:
                        mouseup_cell = self.get_cell_under_mouse(*event.pos)
                        if self.in_play and (mouseup_cell and
                                             mouseup_cell is mousedown_cell):
                            self.handle_click(event.button, mouseup_cell)

                        elif not self.in_play and mouseup_cell is None:
                            # The margin has been clicked, restart
                            self.init_game()

                    mousedown_cell = None
                    mousedown_button = None

            dirty_rects += self.check_winning_state()

            # Director acting!
            if self.in_play and self.director:
                if self.frame >= self.director_act_at:
                    director_redraw_cells = self.director_cell_redraw
                    self.director_cell_redraw = []

                    # Perform queued actions
                    self.director_control.exec_queue()
                    dirty_rects += self.check_winning_state()

                    if self.in_play:
                        # Determine next moves
                        self.director_control.reset_cache()
                        self.director.act()
                        self.director_act_at = self.frame + self.director_skip_frames

                    director_acted = True

            for cell in self.board.itervalues():
                if cell.draw():
                    dirty_rects.append(cell)

            if director_acted:
                self.redraw_cells(director_redraw_cells)

                # Display next actions
                dirty_rects += self.draw_director_actions()

            if self._last_mines_left != self.mines_left:
                self.draw_score()
                dirty_rects.append(self.scoreboard_rect)

            if dirty_rects:
                pygame.display.update(dirty_rects)
                dirty_rects = []

            self.clock.tick(self.tick)

        if self.halt:
            pygame.quit()

    def reconfigure_board(self, cell):
        """Moves a mine if it's the first cell clicked"""
        if self.clear_neighbors_of_first_click:
            self._clear_first_click_neighbors(cell)
        else:
            self._clear_first_click_cell(cell)
        self.determine_numbers()

    def _clear_first_click_neighbors(self, cell):
        self._clear_cells(cell.neighbors() + [cell])

    def _clear_first_click_cell(self, cell):
        self._clear_cells([cell])

    def _clear_cells(self, cells):
        all_cells = self.board.values()
        random.shuffle(all_cells)
        for cell in cells:
            if not cell.is_mine:
                continue

            while all_cells:
                possible_cell = all_cells.pop()
                if possible_cell in cells:
                    continue
                if possible_cell.is_mine:
                    continue

                possible_cell.is_mine = True
                cell.is_mine = False
                break

    def did_win(self):
        return all(c.is_mine or c.is_revealed for c in self.board.itervalues())

    def check_winning_state(self):
        if self.did_win():
            self.win()
        return []
