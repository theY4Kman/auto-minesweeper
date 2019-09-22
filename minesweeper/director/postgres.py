import logging
from typing import Dict

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
)
from sqlalchemy.dialects.postgresql import insert, ARRAY, DOUBLE_PRECISION
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    aliased,
    relationship,
    scoped_session,
    Session,
    sessionmaker,
)
from sqlalchemy.orm.exc import StaleDataError

from minesweeper.director.base import Director, register_director, Cell as DirectorCell

logger = logging.getLogger(__name__)


Model = declarative_base()


class CellNeighbor(Model):
    __tablename__ = 'cell_neighbor'

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

    id = Column(Integer, Sequence('observation_id_seq'), primary_key=True)
    cell_idx = Column(Integer, ForeignKey('cell.idx'))
    cells = Column(ARRAY(Integer))
    num_mines_remaining = Column(Integer)


@register_director('postgres')
class PostgresDirector(Director):
    """Use postgres for the heavy lifting
    """

    def __init__(self, *args, database_url=None, **kwargs):
        super(PostgresDirector, self).__init__()

        if database_url is None:
            database_url = os.getenv('DATABASE_URL')

        self.database_url = database_url
        self.engine = None
        self.connect()

        self.last_state: Dict[int, DirectorCell] = {}

    def connect(self):
        self.engine = create_engine(self.database_url, echo='debug')
        logging.getLogger('sqlalchemy.engine').propagate = False

        # intarray makes set logic w/ arrays easier
        self.engine.execute('CREATE EXTENSION IF NOT EXISTS intarray;')

        self._sessionmaker = scoped_session(sessionmaker(bind=self.engine))

        Model.metadata.drop_all(self.engine)
        Model.metadata.create_all(self.engine)

    def update_cells(self):
        mappings = []
        for game_cell in self.control.get_cells():
            if self.last_state.get(game_cell.idx) != game_cell.type:
                self.last_state[game_cell.idx] = game_cell.type
                mappings.append({
                    'idx': game_cell.idx,
                    'x': game_cell.x,
                    'y': game_cell.y,
                    'number': game_cell.number,
                    'is_revealed': game_cell.is_revealed(),
                    'is_flagged': game_cell.is_flagged(),
                })

        try:
            self.session.bulk_update_mappings(Cell.__mapper__, mappings)
        except StaleDataError:
            self.session.rollback()

            self.session.bulk_insert_mappings(Cell.__mapper__, mappings)
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
            self.engine.execute(st)

        self.session.commit()

    def exec_moves(self, moves):
        """Execute moves in the form ('xyz_click', cell)"""
        for move in moves:
            self.exec_move(move)

    def exec_move(self, move):
        attr, cell = move
        getattr(cell, attr)()

    def act(self):
        self.session: Session = self._sessionmaker()

        methods = [
            self.act_deliberately,
            self.act_random_with_lowest_observed_probability,
            self.act_random,
        ]

        try:
            self.update_cells()
            for method in methods:
                if method():
                    logger.info('Acting with %s', method.__name__)
                    break
        finally:
            self._sessionmaker.remove()

    def act_deliberately(self):
        # Clear table first
        self.session.query(Observation).delete()
        self.session.commit()

        self.init_insights()
        self.propagate_observations()

        moves = self.choose_eager_moves()
        if moves:
            self.exec_moves(moves)
            return True

    def init_insights(self):
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

        self.session.execute(insert_observations)
        self.session.commit()

    def propagate_observations(self):
        """Split observations into atomic chunks
        """
        self.split_supersets()
        self.constrict_overlaps()

    def split_supersets(self):
        """Remove strict subets from their superset Observation
        """
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

        self.engine.execute(update_supersets)
        self.session.commit()

    def constrict_overlaps(self):
        """Impose constraints by shrinking observation cells and mines remaining
        """
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

        self.engine.execute(update_constricted)
        self.session.commit()

    def choose_eager_moves(self):
        # REVELATIONS ---
        # Any time num_mines_remaining is 0, we know it would be impossible to
        # have a mine in the cell. So, uh, click it.
        st = self.session.query(
            func.unnest(Observation.cells).label('cell_idx')
        )
        st = st.select_from(Observation)
        st = st.filter(Observation.num_mines_remaining == 0)
        revelation_cells = st.cte('revelation_cells')

        st = self.session.query(
            literal('click'),
            Cell.x,
            Cell.y,
        )
        st = st.select_from(revelation_cells)
        st = st.join(Cell, revelation_cells.c.cell_idx == Cell.idx)
        st = st.filter(Observation.num_mines_remaining == 0)
        to_reveal = st

        # FLAGELLATIONS ---
        # First, grab the number of cells in each observation, which must occur
        # in a CTE
        st = self.session.query(
            func.unnest(Observation.cells).label('cell_idx')
        )
        st = st.select_from(Observation)
        st = st.filter(Observation.num_mines_remaining == func.cardinality(Observation.cells))
        flagellation_cells = st.subquery('flagellation_cells')

        # Now, any time num_mines_remaining of an observation are the same as
        # the number of cells it references, we are certain all those cells have
        # mines. So, uh, right click em.
        st = self.session.query(
            literal('right_click'),
            Cell.x,
            Cell.y,
        )
        st = st.select_from(flagellation_cells)
        st = st.join(Cell, flagellation_cells.c.cell_idx == Cell.idx)
        to_flag = st

        all_moves = to_reveal.union(to_flag)

        return [
            (action, self.control.get_cell(x, y))
            for action, x, y in all_moves
        ]

    def act_random_with_lowest_observed_probability(self):
        """Choose an unrevealed cell with the lowest probability of being a mine
        """
        st = self.session.query(
            (
                cast(Observation.num_mines_remaining, DOUBLE_PRECISION) / func.cardinality(Observation.cells)
            ).label('probability'),
            func.unnest(Observation.cells).label('cell_idx')
        )
        st = st.filter(func.cardinality(Observation.cells) > 0)
        raw_cell_probabilities = st.subquery('raw_cell_probabilities')

        st = self.session.query(
            func.max(raw_cell_probabilities.c.probability).label('probability'),
            raw_cell_probabilities.c.cell_idx,
        )
        st = st.group_by(raw_cell_probabilities.c.cell_idx)
        cell_probabilities = st.subquery('cell_probabilities')

        st = self.session.query(
            Cell.x,
            Cell.y,
            cell_probabilities.c.probability,
        )
        st = st.select_from(cell_probabilities)
        st = st.join(Cell, Cell.idx == cell_probabilities.c.cell_idx)
        st = st.order_by(cell_probabilities.c.probability)
        choices = st

        choice = choices.first()
        if not choice:
            return False

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
        return True

    def act_random(self):
        qs = self.session.query(Cell)
        qs = qs.filter_by(is_revealed=False, is_flagged=False)
        qs = qs.order_by(func.random())

        random_cell = qs.first()
        game_cell = self.control.get_cell(random_cell.x, random_cell.y)
        game_cell.click()
        return True
