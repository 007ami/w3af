'''
HTTPRequest.py

Copyright 2010 Andres Riancho

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
import copy
import urllib2

from core.data.dc.headers import Headers
from core.data.parsers.url import URL

CR = '\r'
LF = '\n'
CRLF = CR + LF
SP = ' '


class HTTPRequest(urllib2.Request):

    def __init__(self, url, data=None, headers=Headers(),
                 origin_req_host=None, unverifiable=False,
                 follow_redir=True, cookies=True, cache=False, method=None):
        '''
        This is a simple wrapper around a urllib2 request object which helps
        with some common tasks like serialization, cache, etc.

        @param method: None means "choose the method in the default way":
                            if self.has_data():
                                return "POST"
                            else:
                                return "GET"
        '''
        #
        # Save some information for later access in an easier way
        #
        self.url_object = url
        self.follow_redir = follow_redir
        self.cookies = cookies
        self.get_from_cache = cache

        self.method = method
        if self.method is None:
            self.method = 'POST' if data else 'GET'
        
        headers = dict(headers)

        # Call the base class constructor
        urllib2.Request.__init__(self, url.url_encode(), data,
                                 headers, origin_req_host, unverifiable)
    
    def __eq__(self, other):
        return self.get_method() == other.get_method() and\
               self.get_uri() == other.get_uri() and\
               self.get_headers() == other.get_headers() and\
               self.get_data() == other.get_data()
    
    def get_method(self):
        return self.method

    def set_method(self, method):
        self.method = method
            
    def get_uri(self):
        return self.url_object
    
    def get_headers(self):
        headers = Headers(self.headers.items())
        headers.update(self.unredirected_hdrs.items())
        return headers

    def get_request_line(self):
        '''Return request line.'''
        return "%s %s HTTP/1.1%s" % (self.get_method(),
                                     self.get_uri().url_encode(),
                                     CRLF)    
    def to_dict(self):
        serializable_dict = {}
        sdict = serializable_dict
        
        sdict['method'], sdict['uri'] = self.get_method(), self.get_uri().url_string
        sdict['headers'], sdict['data'] = self.get_headers(), self.get_data()
        sdict['follow_redir'], sdict['cookies'] = self.follow_redir, self.cookies
        sdict['cache'] = self.get_from_cache
            
        return serializable_dict
    
    @classmethod    
    def from_dict(cls, unserialized_dict):
        '''
        * msgpack is MUCH faster than cPickle,
        * msgpack can't serialize python objects,
        * I have to create a dict representation of HTTPRequest to serialize it,
        * and a from_dict to have the object back
        
        @param unserialized_dict: A dict just as returned by to_dict()
        '''
        udict = unserialized_dict
        
        method, uri = udict['method'], udict['uri']
        headers, data = udict['headers'], udict['data']
        follow_redir, cookies = udict['follow_redir'], udict['cookies']
        cache = udict['cache']
        
        headers_inst = Headers(headers.items())
        url = URL(uri)
        
        return cls(url, data=data, headers=headers_inst,
                   follow_redir=follow_redir, cookies=cookies, 
                   cache=cache, method=method)
 
        
    def copy(self):
        return copy.deepcopy(self)

    def __repr__(self):
        fmt = '<HTTPRequest "%s" (redir:%s, cookies:%s, cache:%s)>'
        return fmt % (self.url_object.url_string, self.follow_redir,
                      self.cookies, self.get_from_cache)
        