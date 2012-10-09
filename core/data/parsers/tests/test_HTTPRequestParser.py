'''
test_HTTPRequestParser.py

Copyright 2012 Andres Riancho

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
import unittest

from core.data.parsers.HTTPRequestParser import HTTPRequestParser
from core.data.request.HTTPPostDataRequest import HTTPPostDataRequest
from core.data.request.HTTPQsRequest import HTTPQSRequest

from core.controllers.w3afException import w3afException


class TestHTTPRequestParser(unittest.TestCase):

    def test_head_post_data(self):
        fuzzable_request = HTTPRequestParser('POST http://www.w3af.com/ HTTP/1.0', 'foo=bar')
        self.assertIsInstance(fuzzable_request, HTTPPostDataRequest)
        self.assertEqual( fuzzable_request.get_method(), 'POST')
        
    def test_qs(self):
        fuzzable_request = HTTPRequestParser('GET http://www.w3af.com/ HTTP/1.0', '')
        self.assertIsInstance(fuzzable_request, HTTPQSRequest)
        self.assertEqual( fuzzable_request.get_method(), 'GET')

    def test_invalid_url(self):
        self.assertRaises(w3afException, HTTPRequestParser, 'GET / HTTP/1.0', '')

    def test_invalid_protocol(self):
        self.assertRaises(w3afException, HTTPRequestParser, 'ABCDEF', '')

    def test_simple_GET(self):
        http_request = 'GET http://www.w3af.org/ HTTP/1.1\n' \
                       'Host: www.w3af.org\n' \
                       'Foo: bar\n'
                       
        fuzzable_request = HTTPRequestParser(http_request, '')
        self.assertEquals(fuzzable_request.getHeaders(), {'Host': ['www.w3af.org'],
                                                          'Foo': ['bar']})

    def test_POST_repeated(self):
        request_head = 'POST http://www.w3af.org/ HTTP/1.1\n' \
                       'Host: www.w3af.org\n' \
                       'Content-Length: 7\n' \
                       'Foo: spam\n' \
                       'Foo: eggs\n'
                       
        post_data = 'a=1&a=2'
        fuzzable_request = HTTPRequestParser(request_head, post_data)
        self.assertEqual(fuzzable_request.getHeaders(), {'Host': ['www.w3af.org'],
                                                         'Foo': ['spam', 'eggs']})
        self.assertEquals(fuzzable_request.getData(), 'a=1&a=2')
        self.assertEquals(fuzzable_request.getDc(), {'a': ['1', '2']})
        