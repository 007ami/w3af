'''
test_create_fuzzable_requests.py

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

from nose.plugins.attrib import attr
from nose.plugins.skip import SkipTest

from core.data.request.factory import create_fuzzable_requests
from core.data.url.httpResponse import httpResponse
from core.data.parsers.urlParser import url_object

import core.data.kb.config as cf


@attr('smoke')
class TestCreateFuzzableRequests(unittest.TestCase):

    def setUp(self):
        self.url = url_object('http://www.w3af.com/')
        cf.cf.save('fuzzable_headers', [])
        cf.cf.save('fuzzFormComboValues', 'tmb')
    
    def test_not_add_self(self):
        body = ''
        headers = {'content-type': 'text/html'}
        http_response = httpResponse(200, body , headers, self.url, self.url)
        request_lst = create_fuzzable_requests(http_response, add_self=False)
        self.assertEqual( len(request_lst), 0 )

    def test_add_self(self):
        body = ''
        headers = {'content-type': 'text/html'}
        http_response = httpResponse(200, body , headers, self.url, self.url)
        
        request_lst = create_fuzzable_requests(http_response, add_self=True)
        self.assertEqual( len(request_lst), 1 )
        
        fr = request_lst[0]
        self.assertEqual( fr.getURL(), self.url)
    
    def test_redirect_location(self):
        body = ''
        redir_url = 'http://www.w3af.org/'
        headers = {'content-type': 'text/html', 'location': redir_url}
        http_response = httpResponse(200, body , headers, self.url, self.url)
        
        redir_fr = create_fuzzable_requests(http_response, add_self=False)
        self.assertEqual( len(redir_fr), 1 )
        
        redir_fr = redir_fr[0]
        self.assertEqual( redir_fr.getURL().url_string, redir_url)
        
    def test_redirect_uri_relative(self):
        body = ''
        redir_url = '/foo.bar'
        headers = {'content-type': 'text/html', 'uri': redir_url}
        http_response = httpResponse(200, body , headers, self.url, self.url)
        
        redir_fr = create_fuzzable_requests(http_response, add_self=False)
        self.assertEqual( len(redir_fr), 1 )
        
        redir_fr = redir_fr[0]
        self.assertEqual( redir_fr.getURL().url_string, self.url.url_string[:-1] + redir_url)

    raise SkipTest('FIXME: See TODO.')
    def test_body_parse_a(self):
        '''
        TODO: I need to decide if I'm going to implement this in create_fuzzable_requests
              or if I'm going to delegate this responsability to the web_spider plugin
              only.
              
              Note that all the uses of create_fuzzable_requests can be found with:
              
              find . -name '*.py' | xargs grep create_fuzzable_requests
              
              And they all need to be analyzed before making a decision.
        '''
        body = '<a href="http://www.google.com/?id=1">click here</a>'
        headers = {'content-type': 'text/html'}
        http_response = httpResponse(200, body , headers, self.url, self.url)
        
        request_lst = create_fuzzable_requests(http_response, add_self=False)
        self.assertEqual( len(request_lst), 1 )
        
        fr = request_lst[0]
        self.assertEqual( fr.getURL().url_string, 'http://www.google.com/?id=1')
        
    def test_body_parse_form(self):
        body = '''<form action="/foo.bar" method="POST">
                    A: <input name="a" />
                    B: <input name="b" value="123" />
                  </form>'''
        headers = {'content-type': 'text/html'}
        http_response = httpResponse(200, body , headers, self.url, self.url)
        
        post_request_lst = create_fuzzable_requests(http_response, add_self=False)
        self.assertEqual( len(post_request_lst), 1 )
        
        post_request = post_request_lst[0]
        self.assertEqual( post_request.getURL().url_string, 'http://www.w3af.com/foo.bar')
        self.assertEqual( post_request.getData(), 'a=&b=123')
        self.assertEqual( post_request.get_method(), 'POST')

    def test_cookie(self):
        body = ''
        redir_url = '/foo.bar'
        headers = {'content-type': 'text/html', 'uri': redir_url, 'cookie': 'abc=def'}
        http_response = httpResponse(200, body , headers, self.url, self.url)
        
        redir_fr_cookie = create_fuzzable_requests(http_response, add_self=False)
        self.assertEqual( len(redir_fr_cookie), 1 )
        
        redir_fr_cookie = redir_fr_cookie[0]
        self.assertEqual( str(redir_fr_cookie.getCookie()), 'abc=def;')
