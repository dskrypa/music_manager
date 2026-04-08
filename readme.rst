Music Manager
=============

This project has 2 major components:

- Music Manager: Automatically matches song files to artist / album info in wikis to normalize tag values and fill in
  missing info.  Especially useful for multi-language music.  Different online stores use different tags, and many
  don't provide both an english + original title for tracks that have both.
- Plex Manager: Utility for syncing playlists in Plex based on custom rules, for syncing Plex ratings to/from files,
  and for rating tracks in a way that supports specifying 1/2 stars (due to lack of web UI support)

Both components now include a GUI.


Usage / Workflow
----------------

Open an album:

.. image:: https://raw.githubusercontent.com/dskrypa/music_manager/refs/heads/main/docs/_src/images/open_album.png
  :alt: Screenshot of opening an album

View an album:

.. image:: https://raw.githubusercontent.com/dskrypa/music_manager/refs/heads/main/docs/_src/images/view_album.png
  :alt: Screenshot of the album view

View all tags:

.. image:: https://raw.githubusercontent.com/dskrypa/music_manager/refs/heads/main/docs/_src/images/view_all_tags.png
  :alt: Screenshot of the all tags view

Update via Wiki Options:

.. image:: https://raw.githubusercontent.com/dskrypa/music_manager/refs/heads/main/docs/_src/images/wiki_update_options.png
  :alt: Screenshot of options available when updating via Wiki

Update diff:

.. image:: https://raw.githubusercontent.com/dskrypa/music_manager/refs/heads/main/docs/_src/images/wiki_update_diff.png
  :alt: Screenshot of the tag diff when updating via Wiki

View the album after applying changes:

.. image:: https://raw.githubusercontent.com/dskrypa/music_manager/refs/heads/main/docs/_src/images/view_album_after.png
  :alt: Screenshot of the album view after applying changes


Installation
------------

This package can be installed and updated via `pip <https://pip.pypa.io/en/stable/getting-started/>`__::

    $ pip install git+https://github.com/dskrypa/music_manager
