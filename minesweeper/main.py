import argparse

from minesweeper import Game, AttemptUnoDirector


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Minesweeper with an AI interface')

    parser.add_argument('-s', '--scenario',
                        type=argparse.FileType('r'),
                        help='Scenario/saved game to load')
    parser.add_argument('-u', '--scenario-unrevealed',
                        type=bool,
                        default=False,
                        help='Load scenario completely unrevealed')
    parser.add_argument('-r', '--repeat',
                        default=False,
                        action='store_true',
                        help='Repeat loaded scenario')
    parser.add_argument('-d', '--director',
                        choices=['none', 'attempt1'],
                        default='attempt1',
                        help='AI director to use (none to disable)')
    parser.add_argument('--director-skip-frames',
                        type=int,
                        default=1,
                        help='Number of frames to skip between director steps')
    parser.add_argument('-m', '--mode',
                        choices=['winxp', 'win7'],
                        default='win7',
                        help='Which minesweeper mode to emulate '
                             '(winxp=clear first clicked cell,'
                             ' win7=clear neighbours of first clicked cell)')
    parser.add_argument('--disable-low-confidence',
                        default=False,
                        action='store_true',
                        help='Disable low-confidence moves by the director')

    args = parser.parse_args(argv)

    game = Game()

    game.director_skip_frames = args.director_skip_frames
    if args.director == 'attempt1':
        director = AttemptUnoDirector(
            disable_low_confidence=args.disable_low_confidence)
        game.set_director(director)

    if args.scenario:
        # We want to manage opening the file ourselves
        args.scenario.close()

        def load_scenario():
            game.load(args.scenario.name, unrevealed=args.scenario_unrevealed)
        if args.repeat:
            def on_margin_clicked():
                game.init_game()
                load_scenario()
            game.on_margin_clicked = on_margin_clicked
        load_scenario()

    game.clear_neighbors_of_first_click = args.mode == 'win7'

    game.run()
