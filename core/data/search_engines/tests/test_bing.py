'''
test_bing.py

Copyright 2006 Andres Riancho

This file is part of w3af, w3af.sourceforge.net .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.

w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

'''
import random
import unittest

from core.data.search_engines.bing import bing
from core.data.url.xUrllib import xUrllib


class test_bing(unittest.TestCase):
    
    def setUp(self):
        self.query, self.limit = random.choice([('big bang theory', 200),
                                                ('two and half man', 37),
                                                ('doctor house', 55)])
        self.bing_se = bing( xUrllib() )
        
    
    def test_get_links_results(self):
        results = self.bing_se.getNResults(self.query, self.limit)
        # Len of results must be le. than limit
        self.assertTrue(len(results) <= self.limit)
        
        # I want to get some results...
        self.assertTrue(len(results) >= 10, results)
        self.assertTrue(len(set([r.URL.getDomain() for r in results])) >= 3, results)
        
        # URLs should be unique
        self.assertTrue(len(results) == len(set([r.URL for r in results])))
