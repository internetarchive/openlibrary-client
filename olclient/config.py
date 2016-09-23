#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    config.py
    ~~~~~~~~~

    Manages client configurations, e.g. OL authentication

    :copyright: (c) 2016 by Internet Archive.
    :license: see LICENSE for more details.
"""

from __future__ import absolute_import, division, print_function

from collections import namedtuple
import os
import sys
import types

try:
    import ConfigParser as configparser
except:
    import configparser

path = os.path.dirname(os.path.realpath(__file__))
approot = os.path.abspath(os.path.join(path, os.pardir))

def getdef(self, section, option, default_value):
    """A utility method which allows ConfigParser to be fill in defaults
    for missing fields and values.
    """
    try:
        return self.get(section, option)
    except:
        return default_value


Credentials = namedtuple(
    'Credentials', ['username', 'password'])


class Config(object):

    """Manages configurations for the Python OpenLibrary API Client"""

    DEFAULTS = {
        u'openlibrary': {
            u'username': u'',
            u'password': u''
        }
    }

    def __init__(self, config_file=None):
        self.config = configparser.ConfigParser()
        self.config.getdef = types.MethodType(getdef, self.config)
        self.config_file = config_file or self.default_config_file
        self.config.read(self.config_file)

        # make sure config exists, else make default config
        if not os.path.exists(self.config_file):
            self.create_default_config()
        else:
            self.get_config()

    @property
    def default_config_file(self):
        """If no config_file name is specified, returns a valid, canonical
        filepath where the config file can live.
        """
        config_dir = os.path.expanduser('~/.config')
        if not os.path.isdir(config_dir):
            return os.path.expanduser('~/.ol')
        return '{0}/ol.ini'.format(config_dir)

    def create_default_config(self):
        """Creates and saves a new config file with the correct default values
        at the appropriate filepath.
        """
        for section in self.DEFAULTS:
            self.config.add_section(section)
            for key, default in self.DEFAULTS[section].items():
                self.config.set(section, key, default)

        if not os.path.exists(self.config_file):
            with open(self.config_file, 'w') as fh:
                os.chmod(self.config_file, 0o600)
                self.config.write(fh)

    def get_config(self):
        """Loads an existing config .ini file from the disk and returns its
        contents as a dict
        """
        config = {}
        for section in self.DEFAULTS:
            config[section] = {}
            for key, default in self.DEFAULTS[section].items():
                config[section][key] = self.config.getdef(section, key, default)

        username = config['openlibrary'].pop('username')
        password = config['openlibrary'].pop('password')
        config['openlibrary']['credentials'] = Credentials(
            username, password) if (username and password) else None

        return config
