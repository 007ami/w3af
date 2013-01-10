'''
logHandler.py

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
import urllib2

import core.controllers.output_manager as om

from core.data.url.HTTPResponse import HTTPResponse
from core.data.dc.headers import Headers
from core.data.request.factory import create_fuzzable_request_from_request


class LogHandler(urllib2.BaseHandler):
    """
    Add an unique id attribute to http responses and then log them.
    """

    handler_order = urllib2.HTTPErrorProcessor.handler_order - 1

    def http_request(self, request):
        '''
        perform some ugly hacking of request headers and go on...
        '''
        #
        # FIXME: What if the user doesn't want to add these headers?
        #
        if not request.has_header('Host'):
            request.add_unredirected_header('Host', request.host)

        if not request.has_header('Accept-encoding'):
            request.add_unredirected_header('Accept-Encoding', 'identity')

        return request

    def http_response(self, request, response):
        self.log_req_resp(request, response)
        return response

    https_request = http_request
    https_response = http_response

    @staticmethod
    def log_req_resp(request, response):
        '''
        Send the request and the response to the output manager.
        '''
        orig_headers = request.unredirected_hdrs.items()
        headers = Headers(orig_headers)
        fr = create_fuzzable_request_from_request(request,
                                                  add_headers=headers)
        if isinstance(response, HTTPResponse):
            resp = response
        else:
            resp = HTTPResponse.from_httplib_resp(response,
                                                  original_url=request.url_object)
            resp.set_id(response.id)

        om.out.log_http(fr, resp)
