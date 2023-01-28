Music Manager
#############

This project has 2 major components:

- Music Manager: Automatically matches song files to artist / album info in wikis to normalize tag values and fill in
  missing info.  Especially useful for multi-language music.  Different online stores use different tags, and many
  don't provide both an english + original title for tracks that have both.
- Plex Manager: Utility for syncing playlists in Plex based on custom rules, for syncing Plex ratings to/from files,
  and for rating tracks in a way that supports specifying 1/2 stars (due to lack of web UI support)

Both components now include a GUI, mostly built using `PySimpleGUI <http://www.PySimpleGUI.org>`_.


Installing Music Manager
************************

Music Manager can be installed and updated via `pip <https://pip.pypa.io/en/stable/getting-started/>`__::

    $ pip install git+https://github.com/dskrypa/music_manager


Links
*****

- Source Code: https://github.com/dskrypa/music_manager
- Issue Tracker: https://github.com/dskrypa/music_manager/issues


Indices and Tables
******************

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. Table of Contents (navigation)

.. toctree::
   :caption: API Documentation
   :maxdepth: 4
   :hidden:

   api

.. toctree::
   :caption: Script Docs
   :maxdepth: 2
   :hidden:

   scripts
