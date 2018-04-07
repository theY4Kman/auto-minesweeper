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
from typing import List

from minesweeper.datastructures import NeighborGraph
from minesweeper.director.base import Cell

random = SystemRandom()

from minesweeper.director.random_director import RandomExpansionDirector


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
            dist_between_last_moves = tuple(self.dist_between_last_moves(num_moves))
            avg_velocity = sum(dist_between_last_moves) / len(dist_between_last_moves)
            slope_x, slope_y = self.slope_to_last_move()
            unit_x, unit_y = slope_x / avg_velocity, slope_y / avg_velocity
            _, (last_x, last_y) = self.history[-1]
            next_move = last_x + unit_x, last_y + unit_y
            logger.debug('Projected next move at %s using avg velocity %s '
                         '(normalized to %s) from last move %s',
                         next_move, avg_velocity, (unit_x, unit_y), (last_x, last_y))
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

    def get_next_moves(self):
        confident_planners = (
            self.obvious,
            self.immediate_grouping,
            self.indirect_grouping,
            self.first_click,
            self.endgame_insight,
        )

        guess_planners = (
            self.expand_cardinally,
            self.expand_randomly,
        )

        # Ask each of our confident planners for their suggested moves
        plans = {planner: planner()
                 for planner in confident_planners}

        # Filter out empty plans
        plans = {planner: plan
                 for planner, plan in plans.items()
                 if plan}

        # Find the planner with the closest move to the last cell acted upon
        closest_plan, closest_planner = None, None
        lowest_dist = float('Inf')
        projected_next_move = self.projected_move_location(num_moves=3)
        for planner, plan in plans.items():
            for action, cell in plan:
                dist = self.dist_between_cell_and_point(cell, *projected_next_move)
                if dist < lowest_dist:
                    lowest_dist = dist
                    closest_plan = plan
                    closest_planner = planner

        if closest_plan:
            logger.info('Chose plan of %s (distance of %f to last cell): %r',
                        closest_planner, lowest_dist, closest_plan)
            return closest_plan

        elif plans:
            random_planner, random_plan = random.choice(tuple(plans.items()))
            logger.info('Randomly chose plan of %s: %r',
                        random_planner, random_plan)
            return random_plan

        elif not self.disable_low_confidence:
            for planner in guess_planners:
                plan = planner()
                if plan:
                    logger.info('Chose guess plan of %s: %r', planner, plan)
                    return plan

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
            neighbors = cell.get_neighbors()
            flagged = [c for c in neighbors if c.is_flagged()]
            unrevealed = [c for c in neighbors if c.is_unrevealed()]

            # If the number of unrevealed neighbours matches our number, flag!
            total_neighbours = len(flagged) + len(unrevealed)
            if unrevealed and total_neighbours == cell.number:
                return [('right_click', c) for c in unrevealed]

            # If the number of flagged neighbours matches our number and we
            # still have unrevealed neighbours, cascade!
            if unrevealed and len(flagged) == cell.number:
                cell.middle_click()
                return [('middle_click', cell)]

    def grouping(self):
        """Deductive reasoning using info from neighbours"""
        return self.immediate_grouping() or self.indirect_grouping()

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
                        return [('click', c) for c in unshared]
                    else:
                        necessary_diff = neighbor_num_flags_left - necessary
                        if necessary_diff == len(unshared):
                            return [('right_click', c) for c in unshared]

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
                        return plan + debug

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
                        return plan + debug

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
            return [('click', cell)]

    def endgame_insight(self):
        """Inference of last flag if only one mine is left"""
        if self.control.get_mines_left() == 1:
            in_play_numbered = [c for c in self._numbered if c.num_flags_left]
            in_play_unrevealed = [c.get_neighbors(is_unrevealed=True)
                                  for c in in_play_numbered]
            shared = reduce(operator.and_, in_play_unrevealed)
            return [('right_click', c) for c in shared]

    def expand_cardinally(self):
        # If no other good choice, expand randomly in a cardinal direction
        # This gives a better chance of being able to use deductive reasoning
        # with groups next turn.
        cardinal_neighbors = set()
        highest_chances = {}
        for cell in self._revealed:
            if not cell.number:
                continue

            neighbors = cell.get_cardinal_neighbors(is_unrevealed=True)
            cardinal_neighbors.update(neighbors)

            unrevealed = cell.get_neighbors(is_unrevealed=True)
            necessary = cell.num_flags_left
            highest_chance = float(necessary) / len(unrevealed) if unrevealed else 0

            for neighbor in neighbors:
                if highest_chance > highest_chances.get(neighbor, -1):
                    highest_chances[neighbor] = highest_chance

        if cardinal_neighbors:
            scored = [(score, cell) for cell, score in highest_chances.items()]
            scored.sort(key=lambda t: t[0])  # sort by highest chance
            score, cell = scored[0]
            logger.debug('Expand cardinally chose %s with score %.3f. Next '
                         'three choices: %s',
                         cell, score,
                         ', '.join('%s (%.2f)' % (score, cell)
                                   for cell, score in scored[1:4]))
            return [('click', cell)]

    def expand_randomly(self):
        # If no cardinal neighbor found, fall back to random expansion
        choices = set()
        for cell in self._revealed:
            neighbors = {c for c in cell.get_neighbors() if c.is_unrevealed()}
            choices.update(neighbors)

        choices = tuple(choices)
        if choices:
            selection = random.choice(choices)
            return [('click', selection)]
