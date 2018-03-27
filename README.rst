Minesweeper Hints
-----------------

A minesweeper clone with an interface for AI directors.

Now Python 3.5+ only, 'cause I like using type annotations to nudge PyCharm into showing me code hints, so's I don't have to type so much. I have weak hands, give me a break. That's not true, don't believe that – my hands are moderately useful, at least.


Installation
============

.. TODO: syntax-highlighting for the below

.. code::

    python setup.py install
    minesweeper


Screenshots
===========

Losses

.. image:: https://user-images.githubusercontent.com/33840/37947632-46aad44c-315a-11e8-8286-8ff0bfa226bb.gif

.. image:: https://user-images.githubusercontent.com/33840/37947931-a4aacace-315b-11e8-9845-b3a72a8a6b6b.gif

.. image:: https://user-images.githubusercontent.com/33840/37947736-a7b28f32-315a-11e8-95b4-cae73f413611.gif

Wins

.. image:: https://user-images.githubusercontent.com/33840/37947653-592b7e82-315a-11e8-98b2-a4d256777738.gif

.. image:: https://user-images.githubusercontent.com/33840/37947897-7402df88-315b-11e8-9bfa-becbf8b14e85.gif

*NOTE: The frequency of losses to wins experienced at time of writing is not reflected by the ratio of loss pictures to win pictures. Minesweeper is an unforgiving son of a beast (bitch). Most games are losses, at time of writing.


Command-line Help
=================

.. code::

    usage: minesweeper [-h] [-s SCENARIO] [-u SCENARIO_UNREVEALED] [-r]
                       [-d {none,attempt1}]
                       [--director-skip-frames DIRECTOR_SKIP_FRAMES]
                       [-m {winxp,win7}] [--disable-low-confidence] [-v]

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
      --disable-low-confidence
                            Disable low-confidence moves by the director
      -v, --verbose         increase output verbosity
