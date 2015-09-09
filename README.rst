Minesweeper Hints
-----------------

A minesweeper clone with an interface for AI directors.


Installation
============

.. TODO: syntax-highlighting for the below

.. code::

    python setup.py install
    minesweeper


Command-line Help
=================

.. code::

    usage: minesweeper [-h] [-s SCENARIO] [-u SCENARIO_UNREVEALED] [-r]
                       [-d {none,attempt1}]
                       [--director-skip-frames DIRECTOR_SKIP_FRAMES]
                       [-m {winxp,win7}]
    
    Minesweeper with an AI interface
    
    optional arguments:
      -h, --help            show this help message and exit
      -s SCENARIO, --scenario SCENARIO
                            Scenario/saved game to load
      -u SCENARIO_UNREVEALED, --scenario-unrevealed SCENARIO_UNREVEALED
                            Load scenario completely unrevealed
      -r, --repeat          Repeat loaded scenario
      -d {none,attempt1}, --director {none,attempt1}
                            AI director to use (none to disable)
      --director-skip-frames DIRECTOR_SKIP_FRAMES
                            Number of frames to skip between director steps
      -m {winxp,win7}, --mode {winxp,win7}
                            Which minesweeper mode to emulate (winxp=clear first
                            clicked cell, win7=clear neighbours of first clicked
                            cell)
