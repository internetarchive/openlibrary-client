openlibrary-client
==================

A reference client library for the OpenLibrary API

Notes: Tested with Python 2.7, assumed 3.4 compatibility

- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Testing](#testing)
- [Other Client Libraries](#other-client-libraries)

## Installation

As a prerequisite, openlibrary-client requires libssl-dev for the
cryptography used in openssl:

    $ sudo apt-get install libssl-dev

If you plan on doing MARC parsing, you'll need `yaz` (see:
https://github.com/indexdata/yaz). Assuming ubuntu/debian, you can
install `yaz` via apt-get:

    $ sudo apt-get install yaz

To install the openlibrary-client package:

    $ git clone https://github.com/internetarchive/openlibrary-client.git
    $ cd openlibrary-client
    $ pip install .

## Configuration

Many OpenLibrary actions (like creating Works and Editions) require
authentication, i.e. certain requests must be provided a valid cookie
of a user which has been logged in with their openlibrary account
credentials.  The openlibrary-client can be configured to "remember
you" so you don't have to provide credentials with each request.

First time users may run the following command to enable the "remember
me" feature. This process will ask for a username and password and
save them in ~/.config/ol.ini (or whichever config location the user
has specified). In the next version, the password will not be stored;
instead the account will be authenticated and the username and
resulting cookie (and not the password) will be stored in the config:

    $ ol --configure --username mekarpeles
    password: ***********
    Successfully configured

## Usage

### Python Library

#### Works

Fun things you can do with an Work:

    >>> from olclient.openlibrary import OpenLibrary
    >>> ol = OpenLibrary()
    >>> work = ol.Work.get(u'OL12938932W')
    >>> editions = work.editions

One thing to consider in the snippet above is that work.editions is a
@property which makes several http requests to OpenLibrary in order to
populate results. Once a call has been made to work.editions, its
editions are saved/cached as work._editions.

#### Editions

Fun things you can do with an Edition:

    >>> from olclient.openlibrary import OpenLibrary
    >>> ol = OpenLibrary()
    >>> edition = ol.Edition.get(u'OL25952968M')
    >>> authors = edition.authors
    >>> work = edition.work
    >>> work.add_bookcover(u'https://covers.openlibrary.org/b/id/7451891-L.jpg')
    >>> edition.add_bookcover(u'https://covers.openlibrary.org/b/id/7451891-L.jpg')

### Command Line Tool

Installing the openlibrary-client library will also install the `ol`
command line utility. Right now it does exactly nothing.

    $ ol

    ~usage: ol [-h] [-v] [--get-work] [--get-book] [--get-olid] [--olid OLID]
               [--isbn ISBN] [--title TITLE]

    olclient

    optional arguments:
      -h, --help     show this help message and exit
      -v             Displays the currently installed version of ol
      --get-work     Get a work by --title, --olid
      --get-book     Get a book by --isbn, --olid
      --get-olid     Get an olid by --title or --isbn
      --olid OLID    Specify an olid as an argument
      --isbn ISBN    Specify an isbn as an argument
      --title TITLE  Specify a title as an argument

## Testing

To run test cases (from the openlibrary-client directory):

    $ py.test tests/

## Other Client Libraries

Other OpenLibrary client libraries include:
- Ruby: https://github.com/jayfajardo/openlibrary
- Javascript: https://github.com/onaclovtech/openlibrary
- Python: https://github.com/felipeborges/python-openlibrary and https://github.com/the-metalgamer/python-openlibrary-client
- PHP: https://github.com/beezus/openlibrary-php
