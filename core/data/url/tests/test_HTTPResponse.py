# -*- coding: utf-8 -*-
'''
test_HTTPResponse.py

Copyright 2011 Andres Riancho

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
import cPickle

from nose.plugins.attrib import attr
from nose.plugins.skip import SkipTest

from core.data.url.HTTPResponse import HTTPResponse, DEFAULT_CHARSET
from core.data.misc.encoding import smart_unicode, ESCAPED_CHAR
from core.data.parsers.url import URL
from core.data.dc.headers import Headers

TEST_RESPONSES = {
    'hebrew': (u'ולהכיר טוב יותר את המוסכמות, האופי', 'Windows-1255'),
    'japanese': (u'頴英 衛詠鋭液疫 益駅悦謁越榎厭円', 'EUC-JP'),
    'russian': (u'Вы действительно хотите удалить? Данное действие', 'Windows-1251'),
    'hungarian': (u'Üdvözöljük a SZTAKI webkeresőjében', 'ISO-8859-2'),
    'greek': (u'Παρακαλούμε πριν προχωρήσετε καταχώρηση', 'ISO-8859-7'),
}


@attr('smoke')
class TestHTTPResponse(unittest.TestCase):

    def setUp(self):
        self.resp = self.create_resp(Headers([('Content-Type', 'text/html')]))

    def create_resp(self, headers, body=u'body'):
        url = URL('http://w3af.com')
        return HTTPResponse(200, body, headers, url, url)

    def test_unicode_body_no_charset(self):
        '''
        A charset *must* be passed as arg when creating a new
        HTTPResponse; otherwise expect an error.
        '''
        self.assertRaises(AssertionError, self.resp.getBody)

    def test_rawread_is_none(self):
        '''
        Guarantee that the '_raw_body' attr is set to None after
        used (Memory optimization)
        '''
        resp = self.resp
        resp.setCharset('utf-8')
        # Use the 'raw body'
        _ = resp.getBody()
        self.assertEquals(resp._raw_body, None)

    def test_doc_type(self):

        # Text or HTML
        text_or_html_mime_types = (
            'application/javascript', 'text/html', 'text/xml', 'text/cmd',
            'text/css', 'text/csv', 'text/javascript', 'text/plain'
        )
        for mimetype in text_or_html_mime_types:
            resp = self.create_resp(Headers([('Content-Type', mimetype)]))
            self.assertEquals(
                True, resp.is_text_or_html(),
                "MIME type '%s' wasn't recognized as a valid '%s' type"
                % (mimetype, HTTPResponse.DOC_TYPE_TEXT_OR_HTML)
            )

        # PDF
        resp = self.create_resp(Headers([('Content-Type', 'application/pdf')]))
        self.assertEquals(True, resp.is_pdf())

        # SWF
        resp = self.create_resp(
            Headers([('Content-Type', 'application/x-shockwave-flash')]))
        self.assertEquals(True, resp.is_swf())

        # Image
        image_mime_types = (
            'image/gif', 'image/jpeg', 'image/pjpeg', 'image/png', 'image/tiff',
            'image/svg+xml', 'image/vnd.microsoft.icon'
        )
        for mimetype in image_mime_types:
            resp = self.create_resp(Headers([('Content-Type', mimetype)]))
            self.assertEquals(
                True, resp.is_image(),
                "MIME type '%s' wasn't recognized as a valid '%s' type"
                % (mimetype, HTTPResponse.DOC_TYPE_IMAGE)
            )

    def test_parse_response_with_charset_in_both_headers(self):
        # Ensure that the responses' bodies are correctly decoded (charset in
        # both the http and html). Only http charset is expected to be used.
        for body, charset in TEST_RESPONSES.values():
            hvalue = 'text/html; charset=%s' % charset
            body = ('<meta http-equiv=Content-Type content="text/html;'
                    'charset=utf-16"/>' + body)
            htmlbody = '%s' % body.encode(charset)
            resp = self.create_resp(
                Headers([('Content-Type', hvalue)]), htmlbody)
            self.assertEquals(body, resp.getBody())

    def test_parse_response_with_charset_in_meta_header(self):
        # Ensure responses' bodies are correctly decoded (charset only
        # in the html meta header)
        for body, charset in TEST_RESPONSES.values():
            body = ('<meta http-equiv=Content-Type content="text/html;'
                    'charset=%s/>' % charset)
            htmlbody = '%s' % body.encode(charset)
            resp = self.create_resp(Headers(), htmlbody)
            self.assertEquals(body, resp.body)

    def test_parse_response_with_no_charset_in_header(self):
        # No charset was specified, use the default as well as the default
        # error handling scheme
        for body, charset in TEST_RESPONSES.values():
            html = body.encode(charset)
            resp = self.create_resp(
                Headers([('Content-Type', 'text/xml')]), html)
            self.assertEquals(
                smart_unicode(html, DEFAULT_CHARSET,
                              ESCAPED_CHAR, on_error_guess=False),
                resp.body
            )

    def test_parse_response_with_wrong_charset(self):
        # A wrong or non-existant charset was set; try to decode the response
        # using the default charset and handling scheme
        from random import choice
        for body, charset in TEST_RESPONSES.values():
            html = body.encode(charset)
            headers = Headers([('Content-Type', 'text/xml; charset=%s' %
                                                choice(('XXX', 'utf-8')))])
            resp = self.create_resp(headers, html)
            self.assertEquals(
                smart_unicode(html, DEFAULT_CHARSET,
                              ESCAPED_CHAR, on_error_guess=False),
                resp.body
            )

    def test_eval_xpath_in_dom(self):
        html = """
        <html>
          <head>
            <title>THE TITLE</title>
          </head>
          <body>
            <input name="user" type="text">
            <input name="pass" type="password">
          </body>
        </html>"""
        headers = Headers([('Content-Type', 'text/xml')])
        resp = self.create_resp(headers, html)
        self.assertEquals(2, len(resp.getDOM().xpath('.//input')))

    def test_dom_are_the_same(self):
        resp = self.create_resp(
            Headers([('Content-Type', 'text/html')]), "<html/>")
        domid = id(resp.getDOM())
        self.assertEquals(domid, id(resp.getDOM()))

    def test_get_clear_text_body(self):
        html = 'header <b>ABC</b>-<b>DEF</b>-<b>XYZ</b> footer'
        clear_text = 'header ABC-DEF-XYZ footer'
        headers = Headers([('Content-Type', 'text/html')])
        resp = self.create_resp(headers, html)
        self.assertEquals(clear_text, resp.getClearTextBody())

    def test_get_lower_case_headers(self):
        headers = Headers([('Content-Type', 'text/html')])
        lcase_headers = Headers([('content-type', 'text/html')])

        resp = self.create_resp(headers, "<html/>")

        self.assertEqual(resp.getLowerCaseHeaders(), lcase_headers)
        self.assertIn('content-type', resp.getLowerCaseHeaders())

    def test_pickleable_no_dom(self):
        html = 'header <b>ABC</b>-<b>DEF</b>-<b>XYZ</b> footer'
        headers = Headers([('Content-Type', 'text/html')])
        resp = self.create_resp(headers, html)
        
        pickled_resp = cPickle.dumps(resp)
        unpickled_resp = cPickle.loads(pickled_resp)
        
        self.assertEqual(unpickled_resp, resp)

    def test_pickleable_dom(self):
        
        msg = 'lxml DOM objects are NOT pickleable. This is an impediment for' \
              ' having a multiprocess process that will perform all HTTP requests' \
              ' and return HTTP responses over a multiprocessing Queue.'
        raise SkipTest(msg)
    
    
        html = 'header <b>ABC</b>-<b>DEF</b>-<b>XYZ</b> footer'
        headers = Headers([('Content-Type', 'text/html')])
        resp = self.create_resp(headers, html)
        # This just calculates the DOM and stores it as an attribute, NEEDS
        # to be done before pickling (dumps) to have a real test.
        original_dom = resp.getDOM()
        
        pickled_resp = cPickle.dumps(resp)
        unpickled_resp = cPickle.loads(pickled_resp)
        
        self.assertEqual(unpickled_resp, resp)
        
        unpickled_dom = unpickled_resp.getDOM()
        self.assertEqual(unpickled_dom, original_dom)
        