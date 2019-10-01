import logging
from collections import defaultdict
from contextlib import contextmanager
from typing import Dict, Optional, Any

import os

from sqlalchemy import (
    Boolean,
    Column,
    create_engine,
    ForeignKey,
    func,
    Index,
    Integer,
    literal,
    or_,
    Sequence,
    UniqueConstraint,
    update,
    cast,
    text,
)
from sqlalchemy.dialects.postgresql import insert, ARRAY, DOUBLE_PRECISION
from sqlalchemy.ext import baked
from sqlalchemy.ext.baked import BakedQuery
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    aliased,
    relationship,
    scoped_session,
    Session,
    sessionmaker,
    Query,
)

from minesweeper.director.base import (
    Cell as DirectorCell,
    Director,
    register_director,
)

logger = logging.getLogger(__name__)


Model = declarative_base()


class CellNeighbor(Model):
    __tablename__ = 'cell_neighbor'

    __table_args__ = (
        UniqueConstraint('cell_idx', 'neighbor_idx'),

        # This allows us to create neighbour links entirely in-memory
        Index('cell_neighbor_lookup', 'cell_idx', 'neighbor_idx'),
    )

    cell_idx = Column(ForeignKey('cell.idx'), primary_key=True)
    neighbor_idx = Column(ForeignKey('cell.idx'), primary_key=True)


class Cell(Model):
    __tablename__ = 'cell'
    __table_args__ = (
        UniqueConstraint('x', 'y'),

        # This allows us to create neighbour links entirely in-memory
        Index('cell_x_y_lookup', 'x', 'y', 'idx'),
    )

    idx = Column(Integer, primary_key=True)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    number = Column(Integer)
    is_revealed = Column(Boolean, nullable=False, default=False)
    is_flagged = Column(Boolean, nullable=False, default=False)

    neighbors = relationship('Cell',
                             viewonly=True,
                             secondary=CellNeighbor.__table__,
                             primaryjoin=idx == CellNeighbor.cell_idx,
                             secondaryjoin=CellNeighbor.neighbor_idx == idx)


class Observation(Model):
    __tablename__ = 'observation'
    __table_args__ = (
        Index('observation_size', func.cardinality(text('cells'))),
    )

    id = Column(Integer, Sequence('observation_id_seq'), primary_key=True)
    cell_idx = Column(Integer, ForeignKey('cell.idx'))
    cells = Column(ARRAY(Integer))
    num_mines_remaining = Column(Integer)


@register_director('postgres')
class PostgresDirector(Director):
    """Use postgres for the heavy lifting
    """

    def __init__(self, *args, database_url=None, debug=True, **kwargs):
        super(PostgresDirector, self).__init__(*args, debug=debug, **kwargs)

        if database_url is None:
            database_url = os.getenv('DATABASE_URL')

        self.database_url = database_url
        self.engine = None
        self.session: Session = None
        self.debug = debug
        self.connect()

        self.last_state: Dict[int, DirectorCell] = {}
        self.state: Dict[int, Dict[str, Any]] = {}

        # Use a once-initialized list to store updates, to avoid redundant allocations
        self._cell_updates = []

        # Cache our queries, so we don't incur construction costs in the hot path
        self._insert_observations_query: Optional[Query] = None
        self._split_supersets_query: Optional[Query] = None
        self._constrict_overlaps_query: Optional[Query] = None
        self._baked_eager_moves_query: Optional[BakedQuery] = None
        self._baked_act_lowest_observed_probability_query: Optional[BakedQuery] = None

        # Use a bakery to avoid SQL generation costs
        self.bakery = baked.bakery()

    @contextmanager
    def scoped_session(self) -> Session:
        self.session: Session = self._sessionmaker()

        try:
            yield self.session
            self.session.commit()
        except:
            self.session.rollback()
            raise
        finally:
            self.session.close()

    def connect(self):
        self.engine = create_engine(self.database_url, echo='debug' if self.debug else False)
        logging.getLogger('sqlalchemy.engine').propagate = False

        # intarray makes set logic w/ arrays easier
        self.engine.execute('CREATE EXTENSION IF NOT EXISTS intarray;')

        self._sessionmaker = scoped_session(sessionmaker(bind=self.engine))

        Model.metadata.drop_all(self.engine)
        Model.metadata.create_all(self.engine)

    def reset(self):
        with self.scoped_session():
            self.truncate_cells()
            self.create_cells()

    def truncate_cells(self):
        self.session.execute('''
            TRUNCATE TABLE cell CASCADE;
        ''')
        self.session.commit()

    def create_cells(self):
        width, height = self.control.get_board_size()

        self.session.execute(
            text('''
                WITH board (width, height) AS (
                    VALUES (:width, :height)
                )
                INSERT INTO cell (idx, x, y, number, is_revealed, is_flagged) 
                SELECT
                    x * board.height + y AS idx,
                    x,
                    y,
                    NULL as number,
                    FALSE AS is_revealed,
                    FALSE AS is_flagged
                FROM board,
                     generate_series(0, board.height - 1) AS y,
                     generate_series(0, board.width - 1) AS x;
            '''),
            params=dict(
                width=width,
                height=height,
            )
        )
        self.session.commit()

        # Create our neighbour links using INSERT FROM SELECT
        neighbor = aliased(Cell, name='neighbor')
        st = insert(CellNeighbor)
        st = st.from_select(
            ['cell_idx', 'neighbor_idx'],
            self.session
                .query(Cell.idx, neighbor.idx)
                .select_from(Cell)
                .join(neighbor, or_((Cell.x == neighbor.x + d_x) & (Cell.y == neighbor.y + d_y)
                                    for d_x, d_y in DirectorCell.get_neighbor_deltas()))
        )
        self.session.execute(st)
        self.session.commit()

    def _get_cell_updates(self):
        if not self.state:
            self.state = {
                game_cell.idx: {
                    'idx': game_cell.idx,
                    'number': game_cell.number,
                    'is_revealed': game_cell.is_revealed(),
                    'is_flagged': game_cell.is_flagged(),
                }
                for game_cell in self.control.get_dirty_cells()
            }
            self.last_state = {
                game_cell.idx: game_cell.type
                for game_cell in self.control.get_dirty_cells()
            }
            return {}

        else:
            field_updates = defaultdict(lambda: defaultdict(set))

            for game_cell in self.control.get_dirty_cells():
                if self.last_state.get(game_cell.idx) != game_cell.type:
                    self.last_state[game_cell.idx] = game_cell.type

                    cell_state = self.state[game_cell.idx]

                    if game_cell.number != cell_state['number']:
                        field_updates['number'][game_cell.number].add(game_cell.idx)

                    is_revealed = game_cell.is_revealed()
                    if is_revealed != cell_state['is_revealed']:
                        field_updates['is_revealed'][is_revealed].add(game_cell.idx)

                    is_flagged = game_cell.is_flagged()
                    if is_flagged != cell_state['is_flagged']:
                        field_updates['is_flagged'][is_flagged].add(game_cell.idx)

            return field_updates

    def update_cells(self):
        field_updates = self._get_cell_updates()

        for field, values in field_updates.items():
            for value, cell_ids in values.items():
                st = update(Cell)
                st = st.values(**{field: value})
                st = st.where(Cell.idx.in_(cell_ids))
                self.session.execute(st)

        self.session.commit()

    def exec_moves(self, moves):
        """Execute moves in the form ('xyz_click', cell)"""
        for move in moves:
            self.exec_move(move)

    def exec_move(self, move):
        attr, cell = move
        getattr(cell, attr)()

    def act(self):
        with self.scoped_session():
            methods = [
                self.act_deliberately,
                self.act_lowest_observed_probability,
                self.act_random,
            ]

            self.update_cells()
            for method in methods:
                if method():
                    logger.info('Acting with %s', method.__name__)
                    break

    def act_deliberately(self):
        # Clear table first
        self.engine.execute(f'TRUNCATE {Observation.__tablename__};')
        self.session.commit()

        self.init_insights()
        self.propagate_observations()

        moves = self.choose_eager_moves()
        if moves:
            self.exec_moves(moves)
            return True

    def init_insights(self):
        self.session.execute(self.get_insert_observations_query())
        self.session.commit()

    def get_insert_observations_query(self):
        if self._insert_observations_query is None:
            self._insert_observations_query = self._get_insert_observations_query()

        return self._insert_observations_query

    def _get_insert_observations_query(self):
        cell = aliased(Cell, name='cell')
        neighbor = aliased(Cell, name='neighbor')

        # Grab all unrevealed neighbors of numbered cells, including flagged ones
        # (there may be dupe neighbors, if a numbered cell shares neighbors with
        #  another numbered cell).
        st = self.session.query(
            cell.idx.label('cell_idx'),
            neighbor.idx.label('neighbor_idx'),
            neighbor.is_flagged.label('is_flagged'),
            cell.number.label('original_number'),
            (func.count(neighbor.idx)
                 .filter(neighbor.is_flagged)
                 .over(cell.idx)).label('num_flagged_neighbors'),
        )
        st = st.select_from(CellNeighbor)
        st = st.join(cell, CellNeighbor.cell_idx == cell.idx)
        st = st.join(neighbor, CellNeighbor.neighbor_idx == neighbor.idx)
        st = st.filter(
            cell.number != None,
            ~neighbor.is_revealed,
        )
        st = st.order_by(cell.idx)
        raw_observations_data = st.subquery('raw_observations_data')

        # Filter out our flagged neighbors, and add an index for each unique
        # cell_idx, which will be used to correlate inserted Observations later
        st = self.session.query(
            func.dense_rank().over(order_by=raw_observations_data.c.cell_idx).label('observation_idx'),
            raw_observations_data.c.cell_idx,
            raw_observations_data.c.neighbor_idx,
            (raw_observations_data.c.original_number - raw_observations_data.c.num_flagged_neighbors).label('num_flags_left'),
        )
        st = st.filter(
            ~raw_observations_data.c.is_flagged,
        )
        st = st.order_by(
            raw_observations_data.c.cell_idx
        )
        observations_data = st.cte('observations_data')

        # Insert our observations
        st = insert(Observation)
        st = st.from_select(
            (
                Observation.cell_idx,
                Observation.cells,
                Observation.num_mines_remaining,
            ),
            self.session.query(
                observations_data.c.cell_idx,
                func.array_agg(observations_data.c.neighbor_idx),
                observations_data.c.num_flags_left.label('num_mines_remaining'),
            ).group_by(
                observations_data.c.cell_idx,
                observations_data.c.num_flags_left,
            ).order_by(
                # it's important this ordering matches observations_data's ordering
                observations_data.c.cell_idx
            ),
        )
        st = st.returning(Observation.id)
        insert_observations = st

        return insert_observations

    def propagate_observations(self):
        """Split observations into atomic chunks
        """
        self.split_supersets()
        self.constrict_overlaps()

    def split_supersets(self):
        """Remove strict subets from their superset Observation
        """
        self.engine.execute(self.get_split_supersets_query())
        self.session.commit()

    def get_split_supersets_query(self):
        if self._split_supersets_query is None:
            self._split_supersets_query = self._get_split_supersets_query()

        return self._split_supersets_query

    def _get_split_supersets_query(self):
        superset = aliased(Observation, name='superset')
        subset = aliased(Observation, name='subset')

        st = self.session.query(
            superset.id.label('superset_id'),
            superset.cells.label('superset_cells'),
            superset.num_mines_remaining.label('superset_remaining'),
            subset.cells.label('subset_cells'),
            subset.num_mines_remaining.label('subset_remaining'),
        )
        st = st.select_from(superset, subset)
        st = st.filter(
            superset.id != subset.id,
            superset.cells.contains(subset.cells),
            superset.cells != subset.cells,
        )
        overlaps = st.subquery('overlaps')

        st = update(Observation)
        st = st.values(
            cells=overlaps.c.superset_cells - overlaps.c.subset_cells,
            num_mines_remaining=overlaps.c.superset_remaining - overlaps.c.subset_remaining,
        )
        st = st.where(Observation.id == overlaps.c.superset_id)
        update_supersets = st

        return update_supersets

    def constrict_overlaps(self):
        """Impose constraints by shrinking observation cells and mines remaining
        """
        self.engine.execute(self.get_constrict_overlaps_query())
        self.session.commit()

    def get_constrict_overlaps_query(self):
        if self._constrict_overlaps_query is None:
            self._constrict_overlaps_query = self._get_constrict_overlaps_query()

        return self._constrict_overlaps_query

    def _get_constrict_overlaps_query(self):
        constrictor = aliased(Observation, name='constrictor')
        constricted = aliased(Observation, name='constricted')

        st = self.session.query(
            constrictor.cells.label('constrictor_cells'),
            constrictor.num_mines_remaining.label('constrictor_remaining'),
            constricted.id.label('constricted_id'),
            constricted.cells.label('constricted_cells'),
            constricted.num_mines_remaining.label('constricted_remaining'),
        )
        st = st.select_from(constrictor, constricted)
        st = st.filter(
            constrictor.id != constricted.id,
            constrictor.cells.overlap(constricted.cells),
            constrictor.cells != constricted.cells,
            constrictor.num_mines_remaining == 1,  # TODO: generalize this
            constricted.num_mines_remaining > constrictor.num_mines_remaining,
        )
        constrictions = st.subquery('constrictions')

        st = update(Observation)
        st = st.values(
            cells=constrictions.c.constricted_cells - constrictions.c.constrictor_cells,
            num_mines_remaining=constrictions.c.constricted_remaining - constrictions.c.constrictor_remaining,
        )
        st = st.where(Observation.id == constrictions.c.constricted_id)
        update_constricted = st

        return update_constricted

    def choose_eager_moves(self):
        # XXX: using the cached version of the query ends up freezing the app. idk why
        eager_moves = self.get_eager_moves_query()
        return [
            (action, self.control.get_cell(x, y))
            for action, x, y in eager_moves
        ]

    def get_eager_moves_query(self):
        return self.session.execute('''

            SELECT 
                'click',
                cell.x,
                cell.y
            FROM (
                SELECT unnest(observation.cells) AS cell_idx
                FROM observation
                WHERE observation.num_mines_remaining = 0
            ) AS revelation_cells
            JOIN cell 
                ON revelation_cells.cell_idx = cell.idx

            UNION
            SELECT 
                'right_click',
                cell.x,
                cell.y
            FROM (
                SELECT unnest(observation.cells) AS cell_idx
                FROM observation
                WHERE observation.num_mines_remaining = cardinality(observation.cells)
            ) AS flagellation_cells
            JOIN cell 
                ON flagellation_cells.cell_idx = cell.idx

        ''')

    def act_lowest_observed_probability(self):
        """Choose an unrevealed cell with the lowest probability of being a mine
        """
        choices = self.get_act_lowest_observed_probability_query()
        if not choices:
            return False

        choice, *others = choices

        st = self.session.query(func.count(Cell.idx))
        st = st.filter_by(is_revealed=False, is_flagged=False)
        total_unrevealed_count = st.scalar()

        base_probability = self.control.get_mines_left() / total_unrevealed_count

        # Only act if lowest observed probability is less than the probability
        # of hitting a mine when selecting *any* cell at random
        if choice.probability >= base_probability:
            return False

        game_cell = self.control.get_cell(choice.x, choice.y)
        game_cell.click()

        # Mark the other choices, to inform viewer
        for cell in others:
            game_cell = self.control.get_cell(cell.x, cell.y)

            if cell.probability < 0.34:
                game_cell.mark1()
            elif cell.probability < 0.5:
                game_cell.mark2()
            else:
                game_cell.mark3()

        return True

    def get_act_lowest_observed_probability_query(self):
        if self._baked_act_lowest_observed_probability_query is None:
            self._baked_act_lowest_observed_probability_query = (
                self.bakery(self._get_act_lowest_observed_probability_query)
            )

        return self._baked_act_lowest_observed_probability_query.for_session(self.session)

    def _get_act_lowest_observed_probability_query(self, session):
        num_mines_remaining = cast(Observation.num_mines_remaining, DOUBLE_PRECISION)

        st = session.query(
            (num_mines_remaining / func.cardinality(Observation.cells)).label('probability'),
            func.unnest(Observation.cells).label('cell_idx')
        )
        st = st.filter(func.cardinality(Observation.cells) > 0)
        raw_cell_probabilities = st.subquery('raw_cell_probabilities')

        st = session.query(
            func.max(raw_cell_probabilities.c.probability).label('probability'),
            raw_cell_probabilities.c.cell_idx,
        )
        st = st.group_by(raw_cell_probabilities.c.cell_idx)
        cell_probabilities = st.subquery('cell_probabilities')

        st = session.query(
            Cell.x,
            Cell.y,
            cell_probabilities.c.probability,
        )
        st = st.select_from(cell_probabilities)
        st = st.join(Cell, Cell.idx == cell_probabilities.c.cell_idx)
        st = st.order_by(cell_probabilities.c.probability)
        choices = st

        return choices

    def get_act_lowest_observed_probability_query(self):
        return self.session.execute('''
            
            SELECT 
                cell.x, 
                cell.y, 
                cell_probabilities.probability 
            FROM (
                SELECT 
                    max(raw_cell_probabilities.probability) AS probability, 
                    raw_cell_probabilities.cell_idx AS cell_idx 
                FROM (
                    SELECT 
                        CAST(observation.num_mines_remaining AS DOUBLE PRECISION) / cardinality(observation.cells) AS probability,
                        unnest(observation.cells) AS cell_idx
                    FROM observation
                    WHERE cardinality(observation.cells) > 0
                ) AS raw_cell_probabilities 
                GROUP BY raw_cell_probabilities.cell_idx
            ) AS cell_probabilities 
            JOIN cell 
                ON cell.idx = cell_probabilities.cell_idx 
            ORDER BY cell_probabilities.probability
        
        ''').fetchall()

    def act_random(self):
        qs = self.session.query(Cell)
        qs = qs.filter_by(is_revealed=False, is_flagged=False)
        qs = qs.order_by(func.random())

        random_cell = qs.first()
        if not random_cell:
            return False

        game_cell = self.control.get_cell(random_cell.x, random_cell.y)
        game_cell.click()

        # Mark the other choices, to inform viewer
        for x, y in qs.with_entities(Cell.x, Cell.y)[1:]:
            game_cell = self.control.get_cell(x, y)
            game_cell.mark3()

        return True
