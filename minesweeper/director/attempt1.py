"""
TODO:
 - Grouping deductions amongst cells which don't touch:

    F|2|.       F|2|.
    F|3|.  =>   F|3|.
    .|#|#       .|#|#
    .|2|#       .|2|.

 - Grouping deductions requiring thought among several groups:

    O|#|O     O|#|F
    1|2|#  => 1|2|#
    .|1|O     .|1|O
"""

import logging
import math
import operator
from functools import reduce

from random import SystemRandom
from typing import List, Set

from minesweeper.datastructures import NeighborGraph
from minesweeper.director.base import Cell
from minesweeper.director.random_director import RandomExpansionDirector

random = SystemRandom()

logger = logging.getLogger(__name__)


class AttemptUnoDirector(RandomExpansionDirector):
    def __init__(self, *args, **kwargs):
        self.disable_low_confidence = kwargs.pop('disable_low_confidence',
                                                 False)

        super(AttemptUnoDirector, self).__init__(*args, **kwargs)

        # Cached state for each step
        self._cells: List[Cell] = None
        self._numbered: List[Cell] = None
        self._revealed: List[Cell] = None
        self.history = None

    def sort_by_last_move(self, cells):
        """Sort cells based on location near the last moves"""
        return sorted(cells, key=lambda c: self.avg_dist_to_last_moves(c.x, c.y, num_moves=3))

    def sort_by_momentum_bias(self, cells):
        """Sort cells based on projected next location using average velocity"""
        next_x, next_y = self.projected_move_location(num_moves=3)
        return sorted(cells, key=lambda c: self.dist_between_cell_and_point(c, next_x, next_y))

    def dist_to_last_move(self, x, y):
        return next(self.dist_to_last_moves(x, y, num_moves=1))

    def dist_to_last_moves(self, x, y, num_moves):
        if self.history:
            for _, (l_x, l_y) in self.history[:num_moves]:
                yield math.sqrt((x - l_x)**2 + (y - l_y)**2)
        else:
            yield float('Inf')

    def avg_dist_to_last_moves(self, x, y, num_moves):
        dist_to_last_moves = tuple(self.dist_to_last_moves(x, y, num_moves=num_moves))
        return sum(dist_to_last_moves) / len(dist_to_last_moves)

    def dist_between_last_moves(self, num_moves):
        if self.history[-2:-1]:
            _, (last_x, last_y) = self.history[-1]
            for _, (x, y) in self.history[-(num_moves + 1):]:
                yield self.dist_between_points(last_x, last_y, x, y)
                last_x, last_y = x, y
        else:
            yield float('Inf')

    def slope_to_last_move(self):
        """Return x,y distance to last move"""
        if self.history[-2:-1]:
            _, (a_x, a_y) = self.history[-2]
            _, (b_x, b_y) = self.history[-1]
            return a_x - b_x, a_y - b_y
        else:
            return float('Inf'), float('Inf')

    def dist_between_points(self, a_x, a_y, b_x, b_y):
        return math.sqrt((a_x - b_x)**2 + (a_y - b_y)**2)

    def dist_between_cell_and_point(self, cell, x, y):
        return self.dist_between_points(cell.x, cell.y, x, y)

    def projected_move_location(self, num_moves):
        """Projected location of next move using avg velocity of last moves"""
        if self.history:
            _, (last_x, last_y) = self.history[-1]

            dist_between_last_moves = tuple(self.dist_between_last_moves(num_moves))
            avg_velocity = sum(dist_between_last_moves) / len(dist_between_last_moves)
            if avg_velocity == 0:
                return last_x, last_y

            slope_x, slope_y = self.slope_to_last_move()
            last_dist = dist_between_last_moves[0] or 1
            unit_x, unit_y = slope_x / last_dist, slope_y / last_dist
            next_slope_x, next_slope_y = unit_x * avg_velocity, unit_y * avg_velocity
            next_move = last_x + next_slope_x, last_y + next_slope_y

            logger.debug('Projected next move at %s from %s, '
                         'with slope %s calculated using avg velocity %s '
                         'applied to last slope %s normalized to %s',
                         next_move, (last_x, last_y),
                         (next_slope_x, next_slope_y), avg_velocity,
                         (slope_x, slope_y), (unit_x, unit_y))
            return next_move
        else:
            return float('Inf'), float('Inf')

    def exec_moves(self, moves):
        """Execute moves in the form ('xyz_click', cell)"""
        for move in moves:
            self.exec_move(move)

    def exec_move(self, move):
        attr, cell = move
        getattr(cell, attr)()

    def choose_appealing_cell(self, unrevealed_cells):
        """Pick the most appealing cell to reveal, all confidence being equal"""
        lowest_dist = float('Inf')
        best_cell = None
        projected_next_move = self.projected_move_location(num_moves=3)
        for cell in unrevealed_cells:
            dist = self.dist_between_cell_and_point(cell, *projected_next_move)
            if dist < lowest_dist:
                lowest_dist = dist
                best_cell = cell
        return best_cell, lowest_dist

    def get_next_moves(self):
        # Each planners should return an iterable (or generator) of plans, which
        # are lists of ('action', cell)
        planner_tiers = (
            ('confident', True, (
                self.obvious,
                self.immediate_grouping,
                self.indirect_grouping,
                self.first_click,
                self.endgame_obvious,
                self.endgame_insight,
            )),
            ('heuristic guess', False, (
                self.expand_to_border,
            )),
            ('heuristic guess', False, (
                self.expand_cardinally,
            )),
            ('total guess', False, (
                self.expand_randomly,
            )),
            ('last resort', False, (
                self.choose_randomly,
            )),
        )

        for planner_type, is_confident, planners in planner_tiers:
            plans = [
                (planner, plan)
                for planner in planners
                for plan in planner() or ()
                if plan
            ]

            # Only choose visually appealing plans if all are equally as probable
            # (This seems like it could be generalized to all confidence levels,
            #  but this scratches the itch for now.)
            if is_confident:
                if self.history:
                    revealed_between = {}
                    _, (last_x, last_y) = self.history[-1]
                    last_cell = self.control.get_cell(last_x, last_y)

                    for planner, plan in plans:
                        for action, cell in plan:
                            if cell in revealed_between:
                                continue

                            num_revealed_trace = len(tuple(cell.trace_to(last_cell)))
                            revealed_between[cell] = (num_revealed_trace, planner, plan)

                    if revealed_between:
                        scored_plans = sorted(revealed_between.values(), key=lambda t: t[0])
                        num_revealed_trace, planner, plan = next(iter(scored_plans))

                        logger.info('Chose %s plan of %s (%d unrevelead between): %r',
                                    planner_type, planner.__name__, num_revealed_trace, plan)
                        return plan

                # Find the planner with the closest move to the last cell acted upon
                closest_plan, closest_planner = None, None
                lowest_dist = float('Inf')
                for planner, plan in plans:
                    best_cell, dist = self.choose_appealing_cell(cell for _, cell in plan)
                    if dist < lowest_dist:
                        lowest_dist = dist
                        closest_plan = plan
                        closest_planner = planner

                if closest_plan:
                    logger.info('Chose %s plan of %s (distance of %f to last cell): %r',
                                planner_type, closest_planner.__name__, lowest_dist, closest_plan)
                    return closest_plan

            if plans:
                random_planner, random_plan = random.choice(plans)
                logger.info('Randomly chose %s plan of %s: %r',
                            planner_type, random_planner, random_plan)
                return random_plan

    def act(self):
        # Sorting makes the director more visually appealing by having most
        # moves seem near each other.
        self._cells = self.sort_by_momentum_bias(self.control.get_cells())
        self._numbered = [c for c in self._cells if c.is_number()]
        self._revealed = [c for c in self._cells if c.is_revealed()]

        history = self.control.get_history()
        if history:
            self.history = history

        moves = self.get_next_moves()
        if moves:
            logger.info('Executing moves: %r', moves)
            self.exec_moves(moves)

    def obvious(self):
        """Trivial moves based on game rules

        Examples:

            1. Flagging

                |1|        |1|
                  |#|  ->    |F|
                              ^

            2. Cascading

                |1|#|  ->  |1|
                |#|F|  ->    |F|
                            ^ ^

        """
        for cell in self._numbered:
            unrevealed = cell.get_neighbors(is_unrevealed=True)
            if not unrevealed:
                # Ehhh, who needs you!
                continue

            num_flags_left = cell.num_flags_left

            # If the number of unrevealed neighbours matches our number, flag!
            if len(unrevealed) == num_flags_left:
                yield [('right_click', c) for c in unrevealed]

            # If the number of flagged neighbours matches our number and we
            # still have unrevealed neighbours, cascade!
            if unrevealed and not num_flags_left:
                yield [('middle_click', cell)]

    def grouping(self):
        """Deductive reasoning using info from neighbours"""
        yield from self.immediate_grouping()
        yield from self.indirect_grouping()

    def immediate_grouping(self):
        """Deductive reasoning using info from direct relatives

        Examples:

            |#|2             |#|2
            |#|3 2 2|F|      |#|3 2 2|F|
            |#|#|#|#|2|  ->  |#|F|#|#|2|
            |#|#|#|#|#|      |#|#|#|#|#|
                                ^

        """
        nm = NeighborGraph(self._numbered, lambda n: n.is_unrevealed())

        # Deductive reasoning through grouping
        for cell in self._numbered:
            neighbors = cell.get_neighbors()
            numbered_neighbors = nm.subsets_of(cell) | nm.supersets_of(cell)

            flagged = [c for c in neighbors if c.is_flagged()]
            unrevealed = {c for c in neighbors if c.is_unrevealed()}
            necessary = cell.number - len(flagged)

            for neighbor in numbered_neighbors:
                neighbor_neighbors = neighbor.get_neighbors()
                neighbor_unrevealed = {c for c in neighbor_neighbors
                                       if c.is_unrevealed()}
                if (unrevealed.issubset(neighbor_unrevealed) and
                        unrevealed != neighbor_unrevealed):
                    neighbor_num_flags_left = neighbor.num_flags_left

                    unshared = neighbor_unrevealed - unrevealed
                    if necessary == neighbor_num_flags_left:
                        yield [('click', c) for c in unshared]
                    else:
                        necessary_diff = neighbor_num_flags_left - necessary
                        if necessary_diff == len(unshared):
                            yield [('right_click', c) for c in unshared]

    def indirect_grouping(self):
        """Deductive reasoning using info from extended relatives

        Examples:

            |#|#|1|      |#|#|1|
            |#|#|#|  ->  |#|#|F|
            |1 3|#|      |1 3|#|
               1|#|         1|#|
                              ^

        """
        unrevealed_graph = NeighborGraph(self._numbered, lambda n: n.is_unrevealed())

        for cell in self._numbered:
            cell_needs = cell.num_flags_left
            if not cell_needs:
                continue

            cell_unrevealed = cell.get_neighbors(is_unrevealed=True)

            neighbors = unrevealed_graph.supersets_of(cell)
            for neighbor in neighbors:
                neighbor_needs = neighbor.num_flags_left
                neighbor_unrevealed = neighbor.get_neighbors(is_unrevealed=True)

                insightful_neighbors = unrevealed_graph.subsets_of(neighbor) - {cell}
                for insightful_neighbor in insightful_neighbors:
                    insightful_neighbor_needs = insightful_neighbor.num_flags_left
                    insightful_neighbor_unrevealed = insightful_neighbor.get_neighbors(is_unrevealed=True)

                    if cell_unrevealed.intersection(insightful_neighbor_unrevealed):
                        # If the insightful neighbour shares any of the same
                        # unrevealed spots as cell, well, she wasn't very
                        # insightful, was she?

                        # nah but 4realzies idk how to do anything with that
                        # kind of neighbor. Maybe there is a use, but idk it now

                        continue

                    # Unrevealed neighbours of neighbor, after removing both
                    # cell's and insightful_neighbor's cells
                    staked_cells = neighbor_unrevealed - cell_unrevealed - insightful_neighbor_unrevealed
                    if not staked_cells:
                        continue

                    neighbor_needs_after_insight = neighbor_needs - cell_needs - insightful_neighbor_needs
                    if neighbor_needs_after_insight == 0:
                        logger.debug('Found indirect grouping on staked cells '
                                     'of %s, using info from %s and %s',
                                     neighbor, cell, insightful_neighbor)
                        plan = [('click', c) for c in staked_cells]
                        debug = [
                            ('mark1', neighbor),
                            ('mark2', cell),
                            ('mark3', insightful_neighbor),
                        ]
                        yield plan + debug

                    elif neighbor_needs_after_insight == len(staked_cells):
                        logger.debug('Found indirect grouping on staked cells '
                                     'of %s, using info from %s and %s',
                                     neighbor, cell, insightful_neighbor)
                        plan = [('right_click', c) for c in staked_cells]
                        debug = [
                            ('mark1', neighbor),
                            ('mark2', cell),
                            ('mark3', insightful_neighbor),
                        ]
                        yield plan + debug

    def first_click(self):
        if not self._revealed:
            # For our first turn, choose an edge
            w, h = self.control.get_board_size()
            edges = set()
            for y in range(h):
                edges.add((0, y))
                edges.add((w - 1, y))
            for x in range(w):
                edges.add((x, 0))
                edges.add((x, h - 1))
            edges = list(edges)
            coord = random.choice(edges)
            cell = self.control.get_cell(*coord)
            yield [('click', cell)]

    def endgame_obvious(self):
        """Click on any remaining unrevealed cells if all mines are gone"""
        if self.control.get_mines_left() == 0:
            yield [('click', c) for c in self._cells if c.is_unrevealed()]

    def endgame_insight(self):
        """Inference of final action deduced from number of mines left"""
        in_play_numbered = [c for c in self._numbered if c.num_flags_left]
        in_play_unrevealed = [c.get_neighbors(is_unrevealed=True)
                              for c in in_play_numbered]
        shared = reduce(operator.and_, in_play_unrevealed, set())

        total_unrevealed = sum(1 for c in self._cells if c.is_unrevealed())
        num_mines_left = self.control.get_mines_left()
        if num_mines_left == len(shared):
            yield [('right_click', c) for c in shared]
        elif total_unrevealed - len(shared) == num_mines_left:
            yield [('click', c) for c in shared]

    def expand_to_border(self):
        """Expand onto the border, which can often provide grouping intel
        """
        # XXX: this is maybe getting folded into expand_cardinally
        # border_expanders = {
        #     neighbor
        #     for cell in self._numbered
        #     for neighbor in cell.get_neighbors(is_unrevealed=True,
        #                                        is_on_border=True)
        # }
        # return [('click', cell) for cell in border_expanders]

    def expand_cardinally(self):
        # If no other good choice, expand randomly in a cardinal direction
        # This gives a better chance of being able to use deductive reasoning
        # with groups next turn.
        highest_chances = {}
        for cell in self._numbered:
            unrevealed = len(cell.get_neighbors(is_unrevealed=True))
            if not unrevealed:
                continue

            necessary = cell.num_flags_left
            chance = necessary / unrevealed

            cardinal_neighbors = cell.get_cardinal_neighbors(is_unrevealed=True)
            for neighbor in cardinal_neighbors:
                if chance > highest_chances.get(neighbor, -1):
                    highest_chances[neighbor] = chance

        if not highest_chances:
            return

        scored = [(score, cell) for cell, score in highest_chances.items()]
        scored.sort(key=lambda t: t[0])  # sort by chance, ascending
        high_score, _ = scored[0]
        upper_bound = max(high_score, 0.34)  # heuristic, below 1 in 3 chance,
                                             # I'd rather prefer spots that
                                             # allow for further deduction
        contenders: Set[Cell] = {
            c
            for c, score in highest_chances.items()
            if score <= upper_bound
        }

        # If any are across from another number, filter to them, as they will
        # afford more grouping opportunities, if empty
        grouper_contenders = []
        for contender in contenders:
            for neighbor in contender.get_cardinal_neighbors(is_number=True):
                across = contender.get_cardinal_neighbor_across_from(neighbor)
                if not across or across.is_revealed() or across.is_flagged():
                    logger.debug('Found grouper contender %s across from %s and %s',
                                 contender, neighbor, across)
                    grouper_contenders.append(contender)

        if grouper_contenders:
            logger.debug(
                'Filtered cardinal expansion contenders to groupers %s from %s',
                grouper_contenders, contenders)
            contenders = grouper_contenders

        # Get neighbors across from, across_n
        # Get all the flagged/ neighbors of across_n
        # Subtract the neighbors of cell perpendicular to across_n
        # If there are 8 of those, choose *that* shit


        logger.debug('Expand cardinally offered %d choices with score %.3f: %s',
                     len(contenders), high_score, contenders)
        return [[('click', cell)] for cell in contenders]

    def expand_randomly(self):
        # If no cardinal neighbor found, fall back to random expansion
        choices = {
            neighbor
            for cell in self._numbered
            for neighbor in cell.get_neighbors(is_unrevealed=True)
        }

        return [[('click', cell)] for cell in choices]

    def choose_randomly(self):
        return [[('click', cell)] for cell in self._cells if cell.is_unrevealed()]
