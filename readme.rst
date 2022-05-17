Music Manager
=============

This project has 2 major components:

- Music Manager: Automatically matches song files to artist / album info in wikis to normalize tag values and fill in
  missing info.  Especially useful for multi-language music.  Different online stores use different tags, and many
  don't provide both an english + original title for tracks that have both.
- Plex Manager: Utility for syncing playlists in Plex based on custom rules, for syncing Plex ratings to/from files,
  and for rating tracks in a way that supports specifying 1/2 stars (due to lack of web UI support)

Both components now include a GUI, mostly built using `PySimpleGUI <http://www.PySimpleGUI.org>`_.


Installation
------------

If installing on Linux, you should run the following first::

    $ sudo apt-get install python3-dev


Regardless of OS, setuptools is required (it should already be present in most cases)::

    $ pip install setuptools


All of the other requirements are handled in setup.py, which will be run when you install like this::

    $ pip install git+https://github.com/dskrypa/music_manager
