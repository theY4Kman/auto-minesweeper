import os
import sys
from random import SystemRandom

# This sets up a Context for us; it MUST be an asterisk import
from plotdevice import *

from plotdevice.context import Context, Canvas
from plotdevice.gfx.image import Image
from plotdevice.gfx.typography import CENTER
from plotdevice.util import grid

random = SystemRandom()


ROOT_DIR = os.path.dirname(sys.argv[0])
IMAGE_DIR = os.path.join(ROOT_DIR, 'images')
try:
    os.makedirs(IMAGE_DIR)
except OSError:
    pass


FPS = 60

# Board size in cells
BOARD_SIZE = 32, 16
BOARD_WIDTH, BOARD_HEIGHT = BOARD_SIZE

# Number of mines
MINES = 99

# Width/height of each cell
CELL_PX = 16

# Bezel border width
BORDER_PX = 3
BORDER_PX_0 = BORDER_PX - 1

# Board margin
MARGIN_PX = 10

NUMBER_COLORS = {
    1: 'blue',
    2: 'green',
    3: 'red',
    4: 'darkblue',
    5: 'brown',
    6: 'cyan',
    7: 'black',
    8: 'gray',
}


class Templates(object):
    """Responsible for drawing initial pictures of each possible cell state"""

    def __init__(self):
        """
        :type ctx: plotdevice.context.Context
        """
        self.ctx = Context(Canvas(CELL_PX, CELL_PX))
        self.ctx.clear()

        self._template_fns = {
            'mine': self._draw_mine,
            'mine_losing': lambda ctx: self._draw_mine(ctx, losing=True),
            'mine_unrevealed': self._draw_mine_unrevealed,
            'unrevealed': self._draw_unrevealed,
            'empty': lambda ctx: None,
            'flag': self._draw_flag,
        }
        self._templates = {}

        def build_number_fn(i):
            # Embed constant in closure scope
            return lambda ctx: self._draw_number(ctx, i)
        for i in xrange(1, 9):
            self._template_fns['number%d' % i] = build_number_fn(i)

        self._render_templates()

    def __getitem__(self, item):
        return self._templates[item]

    def _render_templates(self):
        for name, fn in self._template_fns.iteritems():
            tmpl = self._render_template(name, fn)
            self._templates[name] = tmpl
            setattr(self, name, tmpl)

    def _render_template(self, name, fn):
        filename = os.path.join(IMAGE_DIR, name + '.png')
        if not os.path.exists(filename):
            self.ctx.clear()
            with self.ctx.export(filename):
                # Default background colour
                with self.ctx.fill('lightgray'):
                    self.ctx.rect(0, 0, CELL_PX, CELL_PX)
                fn(self.ctx)
            self.ctx.clear()

        return Image(filename)

    def _draw_number(self, ctx, number):
        """
        :type ctx: plotdevice.context.Context
        """
        with ctx.fill(NUMBER_COLORS[number]):
            ctx.align(CENTER)
            t = ctx.text(str(number), x=0, y=CELL_PX, width=CELL_PX,
                         size=11, weight='bold', plot=False)
            w,h = ctx.measure(t)
            t.y = CELL_PX - (float(CELL_PX) - h / 2) / 2
            ctx.plot(t)

    def _draw_mine(self, ctx, losing=False):
        color = 'red' if losing else 'black'
        with ctx.translate(CELL_PX / 2 / 2, CELL_PX / 2 / 2), \
             ctx.fill(color):
            ctx.oval(0, 0, CELL_PX / 2, CELL_PX / 2)

    def _draw_mine_unrevealed(self, ctx):
        """A mine which hasn't been revealed, but the game is over"""
        self._draw_unrevealed(ctx)
        self._draw_mine(ctx)

    def _draw_flag(self, ctx):
        self._draw_unrevealed(ctx)

        flag_w, flag_h = 5, 5
        margin = 4

        with ctx.translate(CELL_PX / 2, margin):
            ctx.strokewidth(2)
            with ctx.stroke('black'), ctx.bezier():
                ctx.moveto(0, 0)
                ctx.lineto(0, CELL_PX - margin * 2)

            ctx.strokewidth(0)
            with ctx.fill('darkred'), ctx.bezier():
                ctx.moveto(0, 0)
                ctx.lineto(flag_w, flag_h / 2)
                ctx.lineto(0, flag_h, close=True)

    def _draw_unrevealed(self, ctx):
        """The signature bezel!"""
        # Start with a light, light grey background
        with ctx.fill('#eee'):
            ctx.rect(0, 0, CELL_PX, CELL_PX)

        with ctx.nostroke():
            # Left, top border
            with ctx.fill('black', 0.1), ctx.bezier():
                ctx.moveto(0, 0)
                ctx.lineto(CELL_PX, 0)
                ctx.lineto(CELL_PX - BORDER_PX_0, BORDER_PX_0)
                ctx.lineto(BORDER_PX_0, BORDER_PX_0)
                ctx.lineto(BORDER_PX_0, CELL_PX - BORDER_PX_0)
                ctx.lineto(0, CELL_PX, close=True)

            # Right, bottom border
            with ctx.fill('black', 0.3), ctx.bezier():
                ctx.moveto(CELL_PX, CELL_PX)
                ctx.lineto(CELL_PX, 0)
                ctx.lineto(CELL_PX - BORDER_PX_0, BORDER_PX_0)
                ctx.lineto(CELL_PX - BORDER_PX_0, CELL_PX - BORDER_PX_0)
                ctx.lineto(BORDER_PX_0, CELL_PX - BORDER_PX_0)
                ctx.lineto(0, CELL_PX)
                ctx.lineto(CELL_PX, CELL_PX, close=True)


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
    def __init__(self, game, x, y,
                 is_mine=False, is_flagged=False, is_revealed=False):
        self.game = game
        self.x = x
        self.y = y

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

    def _get_neighbour(self, dix, diy):
        """dix and diy are grid indexes, not pixels"""
        x = self.x + dix * CELL_PX
        y = self.y + diy * CELL_PX
        return self.game.board.get((x, y))

    def determine_number(self):
        if not self.is_mine:
            self.number = len(self.neighbor_mines())

    def draw(self, ctx):
        if self.should_redraw:
            with ctx.translate(self.x, self.y):
                return self._draw(ctx)

    def _determine_template(self):
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
            else:
                return 'unrevealed'

    def _draw(self, ctx):
        """
        :type ctx: plotdevice.context.Context
        """
        template = self._determine_template()
        if template:
            image = self.game.templates[template]
            ctx.image(image, 0, 0)

    def handle_click(self):
        if not self.is_revealed:
            self.is_revealed = True

            if self.is_mine:
                self.is_losing_mine = True
                self.game.lose()
            elif self.number == 0:
                self.cascade_empty(self)

    def cascade_empty(self, cell):
        """Reveal all neighbours of empty cells, recursively"""
        friendlies = cell.neighbor_friendlies()
        unrevealed = [c for c in friendlies if not c.is_revealed]
        for c in unrevealed:
            c.is_revealed = True
            if c.number == 0:
                self.cascade_empty(c)


class Game(object):
    def __init__(self, ctx):
        """
        :type ctx: plotdevice.context.Context
        """
        self.ctx = ctx
        self.init_ctx()

        self.templates = Templates()

        self.init_game()

    def init_game(self):
        self.lost = False
        self.restart_frame = None

        self.was_mousedown = False
        self.mousedown_cell = None

        self.board = {(x,y): Cell(self, x, y)
                      for x, y in self.grid()}
        self.choose_mines()
        self.determine_numbers()

    def init_ctx(self):
        # Initialize window
        self.ctx.size(BOARD_WIDTH * CELL_PX + MARGIN_PX * 2,
                      BOARD_HEIGHT * CELL_PX + MARGIN_PX * 2)

        self.ctx.speed(FPS)

    def grid(self):
        return grid(BOARD_WIDTH, BOARD_HEIGHT, CELL_PX, CELL_PX)

    def choose_mines(self):
        possibilities = self.board.values()
        random.shuffle(possibilities)
        mines = possibilities[:MINES]
        for cell in mines:
            cell.is_mine = True

    def draw(self, something):
        self.handle_restart()
        self.handle_mouse()

        for x, y in self.grid():
            cell = self.board[x, y]

            # Margin
            with self.ctx.translate(MARGIN_PX, MARGIN_PX):
                cell.draw(self.ctx)

    def handle_mouseup(self):
        mouseup_cell = self.get_cell_under_mouse()
        if mouseup_cell is self.mousedown_cell:
            mouseup_cell.handle_click()

    def handle_mouse(self):
        if self.ctx.mousedown:
            self.mousedown_cell = self.get_cell_under_mouse()
            self.was_mousedown = True
        else:
            if self.was_mousedown:
                self.handle_mouseup()

            # Reset mouse state
            self.was_mousedown = False
            self.mousedown_cell = None

    def get_cell_under_mouse(self):
        x, y = self.ctx.MOUSEX, self.ctx.MOUSEY
        x, y = x - MARGIN_PX, y - MARGIN_PX
        x, y = int(x) / CELL_PX, int(y) / CELL_PX
        x, y = x * CELL_PX, y * CELL_PX
        return self.board[x, y]

    def determine_numbers(self):
        for cell in self.board.itervalues():
            cell.determine_number()

    def lose(self):
        self.lost = True

        for cell in self.board.itervalues():
            cell.is_game_over = True

        self.restart_frame = self.ctx.FRAME + 30

    def handle_restart(self):
        if self.restart_frame and self.ctx.FRAME >= self.restart_frame:
            self.init_game()


class DictProxy(object):
    """Proxy attributes to dict items"""

    def __init__(self, d):
        self.__source = d

    def __getattr__(self, item):
        try:
            return self.__source[item]
        except KeyError:
            raise AttributeError(repr(item))


game = Game(DictProxy(globals()))
draw = game.draw
