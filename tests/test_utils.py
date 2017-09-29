#-*- encoding: utf-8 -*-

"""Test Cases for utilities.""" 

from __future__ import absolute_import, division, print_function

import unittest

from olclient.utils import merge_unique_lists

class TestUtils(unittest.TestCase):

    def test_merge_unique_lists(self):
        test_data = [
            {'in': [[1,2], [2,3]], 'expect': [1, 2, 3]},
            {'in': [[1,2,2,2], [2, 2, 3]], 'expect': [1, 2, 3]},
            {'in': [[9, 10]], 'expect': [9, 10]},
            {'in': [[1, 1, 1, 1]], 'expect': [1]},
            {'in': [], 'expect': []},
            {'in': [[2], [1]], 'expect': [2, 1]}
        ]
        for case in test_data:
            assert(merge_unique_lists(case['in']) == case['expect'])
