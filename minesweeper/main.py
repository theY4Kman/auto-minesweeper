import logging
logging.basicConfig(level=logging.DEBUG)

from configargparse import ArgumentParser, FileType

from minesweeper.director.base import get_directors
from minesweeper import Game


def main(argv=None):
    available_directors = get_directors()

    parser = ArgumentParser(
        description='Minesweeper with an AI interface')

    parser.add_argument('-s', '--scenario',
                        type=FileType('r'),
                        help='Scenario/saved game to load')
    parser.add_argument('--state',
                        help='Game state to load')
    parser.add_argument('-u', '--scenario-unrevealed',
                        type=bool,
                        default=False,
                        help='Load scenario completely unrevealed')
    parser.add_argument('-r', '--repeat',
                        default=False,
                        action='store_true',
                        help='Repeat loaded scenario',
                        env_var='MINESWEEPER_REPEAT_SCENARIO')

    parser.add_argument('--width',
                        type=int,
                        default=60,
                        help='Number of cells to display in each row',
                        env_var='MINESWEEPER_BOARD_WIDTH')
    parser.add_argument('--height',
                        type=int,
                        default=30,
                        help='Number of cells to display in each column',
                        env_var='MINESWEEPER_BOARD_HEIGHT')
    parser.add_argument('--mines',
                        type=int,
                        default=99,
                        help='Number of cells which will contain mines',
                        env_var='MINESWEEPER_NUM_MINES')

    parser.add_argument('-d', '--director',
                        choices=['none'] + list(available_directors),
                        default='attempt2',
                        help='AI director to use (none to disable)',
                        env_var='MINESWEEPER_DIRECTOR')
    parser.add_argument('--director-skip-frames',
                        type=int,
                        default=1,
                        help='Number of frames to skip between director steps')

    parser.add_argument('-m', '--mode',
                        choices=['winxp', 'win7'],
                        default='win7',
                        help='Which minesweeper mode to emulate '
                             '(winxp=clear first clicked cell,'
                             ' win7=clear neighbours of first clicked cell)',
                        env_var='MINESWEEPER_MODE')

    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                        action="store_true")

    parser.add_argument("--debug", help="enable debugging output",
                        action="store_true",
                        env_var='MINESWEEPER_DEBUG')

    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    kwargs = {
        'width': args.width,
        'height': args.height,
        'num_mines': args.mines,
    }

    if args.director:
        director_cls = available_directors.get(args.director)
        director = director_cls(debug=args.debug)
        if director:
            kwargs['director'] = director

    game = Game(**kwargs)
    game.director_skip_frames = args.director_skip_frames

    if args.scenario and args.state:
        raise RuntimeError("Cannot load both game state (--state) and scenario (-s/--scenario)")

    if args.scenario or args.state:
        if args.scenario:
            # We want to manage opening the file ourselves
            args.scenario.close()

            def load_scenario():
                game.load(args.scenario.name, unrevealed=args.scenario_unrevealed)

        elif args.state:
            serialized = args.state.replace('\\n', '\n')

            def load_scenario():
                game.deserialize(serialized)
        else:
            assert False, 'THIS SHOULD NOT HAPPEN'

        if args.repeat:
            def on_margin_clicked():
                game.init_game()
                load_scenario()
            game.on_margin_clicked = on_margin_clicked

        load_scenario()

    game.clear_neighbors_of_first_click = args.mode == 'win7'

    game.run()
