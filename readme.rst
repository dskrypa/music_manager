Music Manager
=============

This project has 2 major components:

- Music Manager: Tag editor that includes automatic tag cleanup and wiki match capabilities to fill in missing info
  automatically
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

    $ pip install git+git://github.com/dskrypa/music_manager


Examples - Old
--------------

Show unique tag info about all files in the current directory::

    $ /c/unix/home/user/git/ds_tools/bin/music_manager.py info . -u '*'
    Tag   Tag Name      Count  Value
    --------------------------------------------------------------------------------
    TPOS  Disk Number       7  1
    TPE2  Album Artist      7  Red Velvet (레드벨벳)
    TALB  Album             7  Summer Magic - Summer Mini Album
    TIT2  Song title        1  Hit That Drum
    TIT2  Song title        1  (Bonus Track) Bad Boy (English Ver.)
    TIT2  Song title        1  한 여름의 크리스마스 (With You)
    TIT2  Song title        1  Mr. E
    TIT2  Song title        1  Power Up
    TIT2  Song title        1  Mosquito
    TIT2  Song title        1  Blue Lemonade
    APIC  Album Cover       7  APIC(encoding=<Encoding.L...a(\xafd\xf2\x0f\xff\xd9')
    TPE1  Artist            7  Red Velvet (레드벨벳)
    TRCK  Track number      1  1
    TRCK  Track number      1  2
    TRCK  Track number      1  3
    TRCK  Track number      1  7
    TRCK  Track number      1  5
    TRCK  Track number      1  4
    TRCK  Track number      1  6
    TDRC  Date              7  20180806
    USLT  Lyrics            1  Pop pop pop Ah ah ah ah\r... 내 입안에 녹아드는\r\n우리 사랑이란 느낌
    USLT  Lyrics            1  불 꺼진 방엔 언제 또 들어왔니 \r\n마치 ...는 자꾸 \r\n선을 넘어 넘어 매너없이 Oh
    USLT  Lyrics            1  Ba-banana Ba-ba-banana-na... power up\r\n놀 때 제일 신나니까요
    USLT  Lyrics            1  두근두근 내 맘을 두드려놓고 \r\n자꾸만 도...m boom boom Hit that drum
    USLT  Lyrics            1  너란 녀석이 있대지\r\n다들 관심 있어 혼자...bum bum-\r\nMystery Mr. E
    USLT  Lyrics            1  하얀 모래 위에 우리 둘\r\n꼭 마치 눈이 ...r\nYeah When I’m with you
    USLT  Lyrics            1  Who dat who dat who dat i...shot another bad boy down
    TCON  Genre             7  Dance


Analyze tag info for all files in the current directory::

    $ /c/unix/home/user/git/ds_tools/bin/music_manager.py info . -c
    Tag   Tag Name      Total  Files  Files %  Per File (overall)  Per File (with tag)  Unique Values
    -------------------------------------------------------------------------------------------------
    APIC  Album Cover       7      7     100%                1.00                 1.00              1
    TALB  Album             7      7     100%                1.00                 1.00              1
    TCON  Genre             7      7     100%                1.00                 1.00              1
    TDRC  Date              7      7     100%                1.00                 1.00              1
    TIT2  Song title        7      7     100%                1.00                 1.00              7
    TPE1  Artist            7      7     100%                1.00                 1.00              1
    TPE2  Album Artist      7      7     100%                1.00                 1.00              1
    TPOS  Disk Number       7      7     100%                1.00                 1.00              1
    TRCK  Track number      7      7     100%                1.00                 1.00              7
    USLT  Lyrics            7      7     100%                1.00                 1.00              7

    Version  Count
    --------------
    ID3v2.4      7


Remove the specified undesirable tags from all files in the current directory::

    $ /c/unix/home/user/git/ds_tools/bin/music_manager.py remove . -t txxx priv wxxx comm
    Removing the following tags from all files:
            COMM: Comments
            PRIV: Private frame
            TXXX: User-defined
            WXXX: User-defined URL
    .\[2018.07.04] #Cookie Jar [1st Japanese Mini Album]\01. #Cookie Jar.mp3: Removing tags: COMM (1), TXXX (1), WXXX (1)
    .\[2018.07.04] #Cookie Jar [1st Japanese Mini Album]\02. Aitai-tai.mp3: Removing tags: COMM (1), TXXX (1), WXXX (1)
    .\[2018.07.04] #Cookie Jar [1st Japanese Mini Album]\03. ’Cause it’s you.mp3: Removing tags: COMM (1), TXXX (1), WXXX (1)
    .\[2018.07.04] #Cookie Jar [1st Japanese Mini Album]\04. Dumb Dumb.mp3: Removing tags: COMM (1), TXXX (1), WXXX (1)
    .\[2018.07.04] #Cookie Jar [1st Japanese Mini Album]\05. Russian Roulette.mp3: Removing tags: COMM (1), TXXX (1), WXXX (1)
    .\[2018.07.04] #Cookie Jar [1st Japanese Mini Album]\06. Red Flavor.mp3: Removing tags: COMM (1), TXXX (1), WXXX (1)

