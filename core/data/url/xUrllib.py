'''
xUrllib.py

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
import httplib
import os
import re
import socket
import threading
import time
import traceback
import urllib, urllib2
import sqlite3

from collections import deque
from errno import ECONNREFUSED, EHOSTUNREACH, ECONNRESET, \
                  ENETDOWN, ENETUNREACH, ETIMEDOUT, ENOSPC

import core.controllers.outputManager as om
import core.data.kb.config as cf
import urlOpenerSettings

from core.controllers.misc.homeDir import get_home_dir
from core.controllers.profiling.memory_usage import dump_memory_usage
from core.controllers.misc.number_generator import consecutive_number_generator as seq_gen
from core.controllers.w3afException import (w3afMustStopException, w3afException,
                                            w3afMustStopByUnknownReasonExc,
                                            w3afMustStopByKnownReasonExc,
                                            w3afMustStopOnUrlError)

from core.data.constants.response_codes import NO_CONTENT
from core.data.parsers.HTTPRequestParser import HTTPRequestParser
from core.data.parsers.urlParser import url_object
from core.data.request.factory import create_fuzzable_request
from core.data.url.handlers.keepalive import URLTimeoutError
from core.data.url.handlers.logHandler import LogHandler
from core.data.url.HTTPResponse import HTTPResponse, from_httplib_resp
from core.data.url.HTTPRequest import HTTPRequest as HTTPRequest
from core.data.url.handlers.localCache import CachedResponse
from core.data.dc.headers import Headers


class xUrllib(object):
    '''
    This is a urllib2 wrapper.
    
    @author: Andres Riancho (andres.riancho@gmail.com)
    '''
    
    def __init__(self):
        self.settings = urlOpenerSettings.urlOpenerSettings()
        self._opener = None
        self._memory_usage_counter = 0
        self._non_targets = None
        
        # For error handling
        self._last_request_failed = False
        self._last_errors = deque(maxlen=10)
        self._error_count = {}
        self._count_lock = threading.RLock()
        
        # User configured options (in an indirect way)
        self._grep_queue_put = None
        self._evasion_plugins = []
        self._paused = False
        self._must_stop = False
        self._ignore_errors_conf = False
    
    def pause(self, pauseYesNo):
        '''
        When the core wants to pause a scan, it calls this method, in order to
        freeze all actions
        
        @param pauseYesNo: True if I want to pause the scan; False to un-pause it.
        '''
        self._paused = pauseYesNo
        
    def stop(self):
        '''
        Called when the user wants to finish a scan.
        '''
        self._must_stop = True
    
    def _call_before_send(self):
        '''
        This is a method that is called before every request is sent. I'm using
        it as a hook implement:
            - The pause/stop feature
            - Memory debugging features
        '''
        self._sleep_if_paused_die_if_stopped()
        
        self._memory_usage_counter += 1
        if self._memory_usage_counter == 150:
            dump_memory_usage()
            self._memory_usage_counter = 0
    
    def _sleep_if_paused_die_if_stopped(self):
        '''
        This method sleeps until self._paused is False.
        '''
        while self._paused:
            time.sleep(0.5)
            
            # The user can pause and then STOP
            if self._must_stop:
                self._must_stop = False
                self._paused = False
                raise w3afMustStopException()
        
        # The user can simply STOP the scan
        if self._must_stop:
            self._must_stop = False
            self._paused = False
            raise w3afMustStopException('')
    
    def end(self):
        '''
        This method is called when the xUrllib is not going to be used anymore.
        '''
        path_join = os.path.join
        try:
            cacheLocation = path_join(get_home_dir(), 'urllib2cache',
                                      str(os.getpid()))
            if os.path.exists(cacheLocation):
                for f in os.listdir(cacheLocation):
                    os.unlink(path_join(cacheLocation, f))
                os.rmdir(cacheLocation)
        except Exception, e:
            om.out.error('Error while cleaning urllib2 cache, exception: %s'
                         % e)
        else:
            om.out.debug('Cleared urllib2 local cache.')
        
    def _init(self):
        if self.settings.need_update or self._opener is None:
            self.settings.need_update = False
            self.settings.build_openers()
            self._opener = self.settings.get_custom_opener()

    def getHeaders(self, uri):
        '''
        @param uri: The URI we want to know the request headers
        
        @return: A Headers object with the HTTP headers that would be added by
                the library when sending a request to uri.
        '''
        req = HTTPRequest( uri )
        req = self._add_headers( req )
        return Headers(req.headers)
    
    def _is_blacklisted(self, uri):
        '''
        If the user configured w3af to ignore a URL, we are going to be applying
        that configuration here. This is the lowest layer inside w3af.
        '''
        if self._non_targets is None:
            non_targets = cf.cf.get('nonTargets') or []
            self._non_targets = set()
            self._non_targets.update([nt_url.uri2url() for nt_url in non_targets])
             
        if uri.uri2url() in self._non_targets:
            msg = 'The URL you are trying to reach (%s) was configured as a' \
                  'non-target. NOT performing the HTTP request and returning an' \
                  ' empty response.'
            om.out.debug(msg % uri)
            return True

        return False
    
    def get_cookies(self):
        '''
        @return: The cookies that this uri opener has collected during this scan.
        '''
        return self.settings.get_cookies()
    
    def sendRawRequest(self, head, postdata, fix_content_len=True):
        '''
        In some cases the xUrllib user wants to send a request that was typed 
        in a textbox or is stored in a file. When something like that happens,
        this library allows the user to send the request by specifying two 
        parameters for the sendRawRequest method:
        
        @parameter head: "<method> <URI> <HTTP version>\r\nHeader: Value\r\nHeader2: Value2..."
        @parameter postdata: The postdata, if any. If set to '' or None, no postdata is sent.
        @parameter fix_content_len: Indicates if the content length has to be fixed or not.
        
        @return: An HTTPResponse object.
        '''
        # Parse the two strings
        fuzz_req = HTTPRequestParser(head, postdata)
        
        # Fix the content length
        if fix_content_len:
            headers = fuzz_req.getHeaders()
            fixed = False
            for h in headers:
                if h.lower() == 'content-length':
                    headers[ h ] = str(len(postdata))
                    fixed = True
            if not fixed and postdata:
                headers[ 'content-length' ] = str(len(postdata))
            fuzz_req.setHeaders(headers)
        
        # Send it
        function_reference = getattr( self , fuzz_req.get_method() )
        return function_reference(fuzz_req.getURI(), data=fuzz_req.getData(),
                                  headers=fuzz_req.getHeaders(), cache=False,
                                  grep=False)
    
    def send_mutant( self, mutant, callback=None, grep=True, cache=True,
                     follow_redir=True, cookies=True):
        '''
        Sends a mutant to the remote web server.
        
        @param callback: If None, return the HTTP response object, else call
                         the callback with the mutant and the http response as
                         parameters.
        
        @return: The HTTPResponse object associated with the request
                 that was just sent.
        '''
        #
        # IMPORTANT NOTE: If you touch something here, the whole framework may
        # stop working!
        #
        uri = mutant.getURI()
        data = mutant.getData()

        # Also add the cookie header; this is needed by the mutantCookie
        headers = mutant.getHeaders()
        cookie = mutant.getCookie()
        if cookie:
            headers['Cookie'] = str(cookie)

        args = (uri,)
        kwargs = {
              'data': data, 
              'headers': headers,
              'grep': grep,
              'cache': cache,
              'follow_redir': follow_redir,
              'cookies': cookies,
              }
        method = mutant.get_method()
        
        functor = getattr(self, method)
        res = functor(*args, **kwargs)
        
        if callback is not None:
            # The user specified a custom callback for analyzing the HTTP response
            # this is commonly used when sending requests in an async way.
            callback(mutant, res)

        return res
            
    def GET(self, uri, data=None, headers=Headers(), cache=False,
            grep=True, follow_redir=True, cookies=True, respect_size_limit=True):
        '''
        HTTP GET a URI using a proxy, user agent, and other settings
        that where previously set in urlOpenerSettings.py .
        
        @param uri: This is the URI to GET, with the query string included.
        @param data: Only used if the uri parameter is really a URL. The data 
                     will be converted into a string and set as the URL object
                     query string before sending.
        @param headers: Any special headers that will be sent with this request
        @param cache: Should the library search the local cache for a response
                      before sending it to the wire?
        @param grep: Should grep plugins be applied to this request/response?
        @param follow_redir: Follow redirects that are generated by this request
        @param cookies: Send stored cookies in request (or not)

        @return: An HTTPResponse object.
        '''
        if not isinstance(uri, url_object):
            raise TypeError('The uri parameter of xUrllib.GET() must be of '
                            'urlParser.url_object type.')

        if not isinstance(headers, Headers):
            raise TypeError('The header parameter of xUrllib.GET() must be of '
                            'Headers type.')

        # Validate what I'm sending, init the library (if needed) and check
        # blacklists.
        #
        self._init()

        if self._is_blacklisted(uri):
            return self._new_no_content_resp(uri, log_it=True)
        
        # TODO: This is an UGLY hack that allows me to download oversized files,
        #       but it shouldn't be implemented like this! It should look more
        #       like the follow_redir parameter.
        if not respect_size_limit:
            max_file_size = cf.cf.get('maxFileSize')
            cf.cf.save('maxFileSize', 10**10)
        #
        # Create and send the request
        #
        if data:
            uri = uri.copy()
            uri.querystring = data
            
        req = HTTPRequest(uri, follow_redir=follow_redir, cookies=cookies)
        req = self._add_headers(req, headers)
        try:
            return self._send(req, cache=cache, grep=grep)
        finally:
            if not respect_size_limit:
                # restore the original value
                cf.cf.save('maxFileSize', max_file_size)

    def _new_no_content_resp(self, uri, log_it=False):
        '''
        Return a new NO_CONTENT HTTPResponse object. Optionally call the
        subscribed log handlers
        
        @param uri: URI string or request object
        
        @param log_it: Boolean that indicated whether to log request
        and response.  
        '''
        # accept a URI or a Request object
        if isinstance(uri, url_object):
            req = HTTPRequest(uri)
        elif isinstance(uri, HTTPRequest):
            req = uri
        else:
            msg = 'The uri parameter of xUrllib._new_content_resp() has to be of'
            msg += ' HTTPRequest of url_object type.'
            raise Exception( msg )

        # Work,
        no_content_response = HTTPResponse(NO_CONTENT, '', Headers(), uri,
                                           uri, msg='No Content')
        if log_it:
            # This also assigns the id to both objects.
            LogHandler.log_req_resp(req, no_content_response)
        
        if no_content_response.id is None:
            no_content_response.id = seq_gen.inc()
            
        return no_content_response
            
    def POST(self, uri, data='', headers=Headers(), grep=True,
             cache=False, follow_redir=True, cookies=True):
        '''
        POST's data to a uri using a proxy, user agents, and other settings
        that where set previously.
        
        @param uri: This is the url where to post.
        @param data: A string with the data for the POST.
        @return: An HTTPResponse object.
        '''
        if not isinstance(uri, url_object):
            raise TypeError('The uri parameter of xUrllib.POST() must be of '
                            'urlParser.url_object type.')            

        if not isinstance(headers, Headers):
            raise TypeError('The header parameter of xUrllib.POST() must be of '
                            'Headers type.')


        #    Validate what I'm sending, init the library (if needed) and check
        #    blacklists.
        #
        self._init()

        if self._is_blacklisted(uri):
            return self._new_no_content_resp(uri, log_it=True)
        
        #
        #    Create and send the request
        #
        req = HTTPRequest(uri, data=data, follow_redir=follow_redir, cookies=cookies)
        req = self._add_headers( req, headers )
        return self._send( req , grep=grep, cache=cache)
    
    def getRemoteFileSize(self, req, cache=True):
        '''
        This method was previously used in the framework to perform a HEAD 
        request before each GET/POST (ouch!) and get the size of the response.
        The bad thing was that I was performing two requests for each resource...
        I moved the "protection against big files" to the keepalive.py module.
        
        I left it here because maybe I want to use it at some point... Mainly
        to call it directly or something.
        
        @return: The file size of the remote file.
        '''
        res = self.HEAD( req.get_full_url(), headers=req.headers, 
                         data=req.get_data(), cache=cache )  
        
        resource_length = None
        for i in res.getHeaders():
            if i.lower() == 'content-length':
                resource_length = res.getHeaders()[ i ]
                if resource_length.isdigit():
                    resource_length = int( resource_length )
                else:
                    msg = 'The content length header value of the response wasn\'t an integer...'
                    msg += ' this is strange... The value is: "' + res.getHeaders()[ i ] + '"'
                    om.out.error( msg )
                    raise w3afException( msg )
        
        if resource_length is not None:
            return resource_length
        else:
            msg = 'The response didn\'t contain a content-length header. Unable to return the'
            msg += ' remote file size of request with id: ' + str(res.id)
            om.out.debug( msg )
            # I prefer to fetch the file, before this om.out.debug was a "raise w3afException",
            # but this didnt make much sense
            return 0
        
    def __getattr__(self, method_name):
        '''
        This is a "catch-all" way to be able to handle every HTTP method.
        
        @parameter method_name: The name of the method being called:
        xurllib_instance.OPTIONS will make method_name == 'OPTIONS'.
        '''
        class AnyMethod(object):
            
            class MethodRequest(HTTPRequest):
                def get_method(self):
                    return self._method
                def set_method(self, method):
                    self._method = method
            
            def __init__(self, xu, method):
                self._xurllib = xu
                self._method = method
            
            def __call__(self, uri, data=None, headers=Headers(), cache=False,
                         grep=True, follow_redir=True, cookies=True):
                '''
                @return: An HTTPResponse object that's the result of
                    sending the request with a method different from
                    "GET" or "POST".
                '''
                if not isinstance(uri, url_object):
                    raise TypeError('The uri parameter of AnyMethod.'
                         '__call__() must be of urlParser.url_object type.')
                
                if not isinstance(headers, Headers):
                    raise TypeError('The headers parameter of AnyMethod.'
                         '__call__() must be of Headers type.')
                    
                self._xurllib._init()
                
                if self._xurllib._is_blacklisted(uri):
                    return self._xurllib._new_no_content_resp(uri, log_it=True)
            
                req = self.MethodRequest(uri, data, follow_redir=follow_redir,
                                         cookies=cookies)
                req.set_method(self._method)
                req = self._xurllib._add_headers(req, headers or {})
                return self._xurllib._send(req, cache=cache,
                                           grep=grep)
        
        return AnyMethod(self, method_name)

    def _add_headers( self , req, headers=Headers() ):
        # Add all custom Headers() if they exist
        for h, v in self.settings.header_list:
            req.add_header( h, v )
        
        for h, v in headers.iteritems():
            req.add_header( h, v )

        return req
    
    def _check_uri( self, req ):
        # BUGBUG!
        #
        # Reason: "unknown url type: javascript" , Exception: "<urlopen error unknown url type: javascript>"; going to retry.
        # Too many retries when trying to get: http://localhost/w3af/global_redirect/2.php?url=javascript%3Aalert
        #
        ###TODO: The problem is that the urllib2 library fails even if i do this
        #        tests, it fails if it finds javascript: in some part of the URL    
        if req.get_full_url().startswith( 'http' ):
            return True
        elif req.get_full_url().startswith( 'javascript:' ) or req.get_full_url().startswith( 'mailto:' ):
            raise w3afException('Unsupported URL: ' +  req.get_full_url() )
        else:
            return False
            
    def _send(self, req, cache=False, useMultipart=False, grep=True):
        '''
        Actually send the request object.
        
        @param req: The HTTPRequest object that represents the request.
        @return: An HTTPResponse object.
        '''
        # This is the place where I hook the pause and stop feature
        # And some other things like memory usage debugging.
        self._call_before_send()

        # Sanitize the URL
        self._check_uri(req)
        
        # Evasion
        original_url = req._Request__original
        original_url_inst = req.url_object
        req = self._evasion(req)
        
        start_time = time.time()
        res = None

        req.get_from_cache = cache

        try:
            res = self._opener.open(req)
        except urllib2.HTTPError, e:
            # We usually get here when response codes in [404, 403, 401,...]
            msg = '%s %s returned HTTP code "%s"' % (req.get_method(),
                                                     original_url,
                                                     e.code)

            from_cache = hasattr(e, 'from_cache')
            flags = ' (id=%s,from_cache=%i,grep=%i)' % (e.id, from_cache, grep)
            msg += flags
            om.out.debug(msg)
            
            # Return this info to the caller
            code = int(e.code)
            headers = Headers(e.info().items())
            geturl_instance = url_object(e.geturl())
            read = self._readRespose(e)
            http_resp = HTTPResponse(code, read, headers, geturl_instance,
                                      original_url_inst, _id=e.id,
                                      time=time.time()-start_time, msg=e.msg,
                                      charset=getattr(e.fp, 'encoding', None))
            
            # Clear the log of failed requests; this request is done!
            req_id = id(req)
            if req_id in self._error_count:
                del self._error_count[req_id]

            # Reset errors counter
            self._zero_global_error_count()
        
            if grep:
                self._grep(req, http_resp)

            return http_resp
        except urllib2.URLError, e:
            # I get to this section of the code if a 400 error is returned
            # also possible when a proxy is configured and not available
            # also possible when auth credentials are wrong for the URI
            
            # Timeouts are not intended to increment the global error counter.
            # They are part of the expected behaviour.
            if not isinstance(e, URLTimeoutError):
                self._increment_global_error_count(e)
            try:
                e.reason[0]
            except:
                raise w3afException('Unexpected error in urllib2 : %s'
                                     % repr(e.reason))

            msg = ('Failed to HTTP "%s" "%s". Reason: "%s", going to retry.' % 
                  (req.get_method(), original_url, e.reason))

            # Log the errors
            om.out.debug(msg)
            om.out.debug('Traceback for this error: %s' %
                         traceback.format_exc())
            req._Request__original = original_url
            # Then retry!
            return self._retry(req, e, cache)
        except sqlite3.Error, e:
            msg = 'A sqlite3 error was raised: "%s".' % e
            if 'disk' in str(e).lower():
                msg += ' Please check if your disk is full.'
            raise w3afMustStopException( msg )
        except w3afMustStopException:
            raise
        except Exception, e:
            # This except clause will catch unexpected errors
            # For the first N errors, return an empty response...
            # Then a w3afMustStopException will be raised
            msg = ('%s %s returned HTTP code "%s"' %
                   (req.get_method(), original_url, NO_CONTENT))
            om.out.debug(msg)
            om.out.debug('Unhandled exception in xUrllib._send(): %s' % e)
            om.out.debug(traceback.format_exc())

            # Clear the log of failed requests; this request is done!
            req_id = id(req)
            if req_id in self._error_count:
                del self._error_count[req_id]

            trace_str = traceback.format_exc()
            parsed_traceback = re.findall('File "(.*?)", line (.*?), in (.*)',
                                          trace_str)
            # Returns something similar to:
            #   [('trace_test.py', '9', 'one'), ('trace_test.py', '17', 'two'),
            #    ('trace_test.py', '5', 'abc')]
            #
            # Where ('filename', 'line-number', 'function-name')

            self._increment_global_error_count(e, parsed_traceback)

            return self._new_no_content_resp(original_url_inst, log_it=True)

        else:
            # Everything went well!
            rdata = req.get_data()
            if not rdata:
                msg = ('%s %s returned HTTP code "%s"' % 
                       (req.get_method(), urllib.unquote_plus(original_url), res.code) )
            else:                
                msg = ('%s %s with data: "%s" returned HTTP code "%s"'
                % (req.get_method(), original_url, urllib.unquote_plus(rdata),
                   res.code))
            
            from_cache = hasattr(res, 'from_cache')
            flags = ' (id=%s,from_cache=%i,grep=%i)' % (res.id, from_cache, grep)
            msg += flags
            om.out.debug(msg)

            http_resp = from_httplib_resp(res, original_url=original_url_inst)
            http_resp.set_id(id=res.id)
            http_resp.set_wait_time(time.time()-start_time)

            # Let the upper layers know that this response came from the
            # local cache.
            if isinstance(res, CachedResponse):
                http_resp.set_from_cache(True)

            # Clear the log of failed requests; this request is done!
            req_id = id(req)
            if req_id in self._error_count:
                del self._error_count[req_id]
            self._zero_global_error_count()

            if grep:
                self._grep(req, http_resp)

            return http_resp

    def _readRespose( self, res ):
        read = ''
        try:
            read = res.read()
        except KeyboardInterrupt:
            raise
        except Exception, e:
            om.out.error(str(e))
        return read
        
    def _retry(self, req, urlerr, cache):
        '''
        Try to send the request again while doing some error handling.
        '''
        req_id = id(req)
        if self._error_count.setdefault(req_id, 1) <= \
                self.settings.getMaxRetrys():
            # Increment the error count of this particular request.
            self._error_count[req_id] += 1            
            om.out.debug('Re-sending request...')
            return self._send(req, cache)
        else:
            # Clear the log of failed requests; this one definitely failed.
            # Let the caller decide what to do
            del self._error_count[req_id]
            raise w3afMustStopOnUrlError(urlerr, req)
    
    def _increment_global_error_count(self, error, parsed_traceback=[]):
        '''
        Increment the error count, and if we got a lot of failures raise a
        "w3afMustStopException" subtype.
        
        @param error: Exception object.

        @param parsed_traceback: A list with the following format:
            [('trace_test.py', '9', 'one'), ('trace_test.py', '17', 'two'),
            ('trace_test.py', '5', 'abc')]
            Where ('filename', 'line-number', 'function-name')

        '''
        if self._ignore_errors_conf:
            return
        
        last_errors = self._last_errors

        if self._last_request_failed:
            last_errors.append((str(error) , parsed_traceback))
        else:
            self._last_request_failed = True
        
        errtotal = len(last_errors)
        
        om.out.debug('Incrementing global error count. GEC: %s' % errtotal)
        
        with self._count_lock:
            if errtotal >= 10 and not self._must_stop:
                # Stop using xUrllib instance
                self.stop()
                # Known reason errors. See errno module for more info on these
                # errors.
                EUNKNSERV = -2 # Name or service not known error
                EINVHOSTNAME = -5 # No address associated with hostname
                known_errors = (EUNKNSERV, ECONNREFUSED, EHOSTUNREACH,
                                ECONNRESET, ENETDOWN, ENETUNREACH,
                                EINVHOSTNAME, ETIMEDOUT, ENOSPC)
                
                msg = ('w3af found too many consecutive errors while performing'
                       ' HTTP requests. Either the web server is not reachable'
                       ' anymore or there is an internal error. The last error'
                       ' message is "%s".')
                
                if parsed_traceback:
                    tback_str = ''
                    for path, line, call in parsed_traceback[-3:]:
                        tback_str += '    %s:%s at %s\n' % (path, line, call)
                    
                    msg += ' The last calls in the traceback are: \n%s' % tback_str
                
                if type(error) is urllib2.URLError:
                    # URLError exceptions may wrap either httplib.HTTPException
                    # or socket.error exception instances. We're interested on
                    # treat'em in a special way.
                    reason_err = error.reason 
                    reason_msg = None
                    
                    if isinstance(reason_err, socket.error):
                        if isinstance(reason_err, socket.sslerror):
                            reason_msg = 'SSL Error: %s' % error.reason
                        elif reason_err[0] in known_errors:
                            reason_msg = str(reason_err)
                    
                    elif isinstance(reason_err, httplib.HTTPException):
                        #
                        #    Here we catch:
                        #
                        #    BadStatusLine, ResponseNotReady, CannotSendHeader, 
                        #    CannotSendRequest, ImproperConnectionState,
                        #    IncompleteRead, UnimplementedFileMode, UnknownTransferEncoding,
                        #    UnknownProtocol, InvalidURL, NotConnected.
                        #
                        #    TODO: Maybe we're being TOO generic in this isinstance?
                        #
                        reason_msg = '%s: %s' % (error.__class__.__name__,
                                             error.args)
                    if reason_msg is not None:
                        raise w3afMustStopByKnownReasonExc(msg % error, reason=reason_err)
                
                errors = [] if parsed_traceback else last_errors
                raise w3afMustStopByUnknownReasonExc(msg % error, errs=errors)                   

    def ignore_errors(self, yes_no):
        '''
        Let the library know if errors should be ignored or not. Basically,
        ignore all calls to "_increment_global_error_count" and don't raise the
        w3afMustStopException.

        @parameter yes_no: True to ignore errors.
        '''
        self._ignore_errors_conf = yes_no
            
    def _zero_global_error_count( self ):
        if self._last_request_failed or self._last_errors:
            self._last_request_failed = False
            self._last_errors.clear()
            om.out.debug('Resetting global error count. GEC: 0')
    
    def set_grep_queue_put(self, grep_queue_put ):
        self._grep_queue_put = grep_queue_put
    
    def set_evasion_plugins( self, evasion_plugins ):
        # I'm sorting evasion plugins based on priority
        def sortFunc(x, y):
            return cmp(x.getPriority(), y.getPriority())
        evasion_plugins.sort(sortFunc)

        # Save the info
        self._evasion_plugins = evasion_plugins
        
    def _evasion( self, request ):
        '''
        @parameter request: HTTPRequest instance that is going to be modified
        by the evasion plugins
        '''
        for eplugin in self._evasion_plugins:
            try:
                request = eplugin.modifyRequest( request )
            except w3afException, e:
                msg = 'Evasion plugin "%s" failed to modify the request. Exception: "%s"'
                om.out.error( msg % (eplugin.getName(), e) )
                
        return request
        
    def _grep(self, request, response):

        url_instance = request.url_object
        domain = url_instance.getDomain()
        
        if self._grep_queue_put is not None and\
           domain in cf.cf.get('targetDomains'):
            
            # Create a fuzzable request based on the urllib2 request object
            fr = create_fuzzable_request(
                                        url_instance,
                                        request.get_method(),
                                        request.get_data(),
                                        Headers(request.headers.items())
                                        )
            
            self._grep_queue_put( (fr, response) )    
