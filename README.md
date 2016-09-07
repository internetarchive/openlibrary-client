openlibrary-client
==================

A reference client library for the OpenLibrary API

Notes: Tested with Python 2.7, assumed 3.4 compatibility

- [Installation](#installation)
- [Usage](#usage)
- [Testing](#testing)
- [Other Client Libraries](#other-client-libraries)

## Installation

    $ git clone git@git.archive.org:openlibrary/openlibrary-client.git
	$ cd openlibrary-client
	$ pip install .

If you plan on doing MARC parsing, you'll need `yaz` (see:
https://github.com/indexdata/yaz). Assuming ubuntu/debian, you can
install `yaz` via apt-get:

    $ sudo apt-get install yaz

## Usage

Installing the openlibrary-client library will also install the `ol`
command line utility. Right now it does exactly nothing.

    $ ol

## Testing

To run test cases (from the openlibrary-client directory):

    $ py.test tests/

## Other Client Libraries

Other OpenLibrary client libraries include:
- Ruby: https://github.com/jayfajardo/openlibrary
- Golang: https://github.com/myearwood/openlibrary
- Javascript: https://github.com/onaclovtech/openlibrary
- Python: https://github.com/felipeborges/python-openlibrary and https://github.com/the-metalgamer/python-openlibrary-client
- PHP: https://github.com/beezus/openlibrary-php
