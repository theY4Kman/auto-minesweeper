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
    parser.add_argument('-d', '--director',
                        choices=['none', 'attempt1'],
                        default='attempt1',
                        help='AI director to use (none to disable)')
    parser.add_argument('--director-skip-frames',
                        type=int,
                        default=1,
                        help='Number of frames to skip between director steps')

    args = parser.parse_args(argv)

    game = Game()

    game.director_skip_frames = args.director_skip_frames
    if args.director == 'attempt1':
        director = AttemptUnoDirector()
        game.set_director(director)

    if args.scenario:
        game.load_fp(args.scenario, unrevealed=args.scenario_unrevealed)

    game.run()
