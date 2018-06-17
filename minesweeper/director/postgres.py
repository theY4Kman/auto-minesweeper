import logging
import os

from sqlalchemy import (
    Boolean,
    Column,
    create_engine,
    ForeignKey,
    func,
    Integer,
    literal,
    Sequence,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    aliased,
    relationship,
    scoped_session,
    Session,
    sessionmaker,
)
from sqlalchemy.orm.exc import StaleDataError

from minesweeper.director.base import Director, register_director

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
    lower_bound = Column(Integer)
    upper_bound = Column(Integer)


class ObservationCell(Model):
    __tablename__ = 'observation_cell'
    __table_args__ = (
        UniqueConstraint('observation_id', 'cell_idx'),
    )

    id = Column(Integer, primary_key=True)
    observation_id = Column(Integer, ForeignKey('observation.id', ondelete='CASCADE'), nullable=False)
    cell_idx = Column(Integer, ForeignKey('cell.idx'), nullable=False)


@register_director('postgres')
class PostgresDirector(Director):
    """Use postgres for the heavy lifting"""

    def __init__(self, *args, database_url=None, **kwargs):
        super(PostgresDirector, self).__init__()

        if database_url is None:
            database_url = os.getenv('DATABASE_URL')

        self.database_url = database_url
        self.engine = None
        self.connect()

    def connect(self):
        self.engine = create_engine(self.database_url, echo='debug')
        logging.getLogger('sqlalchemy.engine').propagate = False

        # Setup some debugging helpers
        self.engine.execute('CREATE EXTENSION IF NOT EXISTS tablefunc;')

        self._sessionmaker = scoped_session(sessionmaker(bind=self.engine))

        Model.metadata.drop_all(self.engine)
        Model.metadata.create_all(self.engine)

    def update_cells(self):
        mappings = [
            {
                'idx': i,
                'x': game_cell.x,
                'y': game_cell.y,
                'number': game_cell.number,
                'is_revealed': game_cell.is_revealed(),
                'is_flagged': game_cell.is_flagged(),
            }
            for i, game_cell in enumerate(self.control.get_cells())
        ]

        try:
            self.session.bulk_update_mappings(Cell.__mapper__, mappings)
        except StaleDataError:
            self.session.rollback()
            self.session.bulk_insert_mappings(Cell.__mapper__, mappings)

            # Also create our neighbor links
            neighbor_links = [
                {'cell_idx': game_cell.idx, 'neighbor_idx': neighbor.idx}
                for game_cell in self.control.get_cells()
                for neighbor in game_cell.get_neighbors()
            ]
            self.session.bulk_insert_mappings(CellNeighbor.__mapper__, neighbor_links)

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

        # TODO: propagate observations

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

        # Inserts our observations, with lower/upper bounds as num_flags_left
        st = insert(Observation)
        st = st.from_select(
            (
                Observation.cell_idx,
                Observation.lower_bound,
                Observation.upper_bound,
            ),
            self.session.query(
                observations_data.c.cell_idx,
                observations_data.c.num_flags_left.label('lower_bound'),
                observations_data.c.num_flags_left.label('upper_bound'),
            ).group_by(
                observations_data.c.cell_idx,
                observations_data.c.num_flags_left,
            ).order_by(
                # it's important this ordering matches observations_data's ordering
                observations_data.c.cell_idx
            ),
        )
        st = st.returning(Observation.id)
        inserted_observations = st.cte('inserted_observations')

        # Tag our inserted observation IDs with the same index as our raw
        # observations data query added to each unique cell_idx
        st = self.session.query(
            func.row_number().over().label('observation_idx'),
            inserted_observations.c.id,
        )
        observations = st.cte('observations')

        # Link our observations to the cells they refer to
        st = insert(ObservationCell)
        st = st.from_select(
            (
                ObservationCell.observation_id,
                ObservationCell.cell_idx,
            ),
            self.session.query(
                observations.c.id,
                observations_data.c.neighbor_idx,
            ).select_from(
                observations_data,
            ).join(
                observations, observations_data.c.observation_idx == observations.c.observation_idx
            ),
        )
        insert_observation_cells = st

        self.session.execute(insert_observation_cells)
        self.session.commit()

    def choose_eager_moves(self):
        # REVELATIONS ---
        # Any time the upper bound is 0, we know it would be impossible to have
        # a mine in the cell. So, uh, click it.
        st = self.session.query(
            literal('click'),
            Cell.x,
            Cell.y,
        )
        st = st.select_from(ObservationCell)
        st = st.join(Observation)
        st = st.join(Cell, ObservationCell.cell_idx == Cell.idx)
        st = st.filter(Observation.upper_bound == 0)
        to_reveal = st

        # FLAGELLATIONS ---
        # First, grab the number of cells in each observation, which must occur
        # in a CTE
        st = self.session.query(
            ObservationCell.observation_id,
            func.count(ObservationCell.id).label('size'),
        )
        st = st.group_by(ObservationCell.observation_id)
        observation_sizes = st.subquery('observation_sizes')

        # Now, any time the bounds of an observation are the same as the number
        # of cells it references, we are certain all those cells have mines.
        # So, uh, right click em.
        st = self.session.query(
            literal('right_click'),
            Cell.x,
            Cell.y,
        )
        st = st.select_from(ObservationCell)
        st = st.join(Observation)
        st = st.join(observation_sizes)
        st = st.join(Cell, ObservationCell.cell_idx == Cell.idx)
        st = st.filter(Observation.lower_bound == Observation.upper_bound,
                       Observation.lower_bound == observation_sizes.c.size)
        to_flag = st

        all_moves = to_reveal.union(to_flag)

        return [
            (action, self.control.get_cell(x, y))
            for action, x, y in all_moves
        ]

    def act_random(self):
        qs = self.session.query(Cell)
        qs = qs.filter_by(is_revealed=False, is_flagged=False)
        qs = qs.order_by(func.random())

        random_cell = qs.first()
        game_cell = self.control.get_cell(random_cell.x, random_cell.y)
        game_cell.click()
        return True
