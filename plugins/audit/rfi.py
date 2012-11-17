'''
rfi.py

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
from __future__ import with_statement

import socket
import BaseHTTPServer

from functools import partial

import core.controllers.output_manager as om
import core.data.kb.knowledge_base as kb
import core.data.kb.vuln as vuln
import core.data.constants.severity as severity
import core.controllers.daemons.webserver as webserver
import core.data.constants.ports as ports

from core.controllers.plugins.audit_plugin import AuditPlugin
from core.controllers.misc.get_local_ip import get_local_ip
from core.controllers.misc.is_private_site import is_private_site
from core.controllers.exceptions import w3afException

from core.data.options.opt_factory import opt_factory
from core.data.options.option_types import STRING, PORT, BOOL
from core.data.options.option_list import OptionList
from core.data.fuzzer.fuzzer import create_mutants
from core.data.fuzzer.utils import rand_alnum
from core.data.parsers.url import URL


class rfi(AuditPlugin):
    '''
    Find remote file inclusion vulnerabilities.
    @author: Andres Riancho (andres.riancho@gmail.com)
    '''

    CONFIG_ERROR_MSG = 'audit.rfi plugin needs to be correctly configured to use.' \
                       ' Please set valid values for local address (eg. 10.5.2.5)' \
                       ' and port (eg. 44449), or use the official w3af site as' \
                       ' the target server for remote inclusions.'

    RFI_TEST_URL = 'http://w3af.sourceforge.net/w3af/rfi.html'

    RFI_ERRORS = ('php_network_getaddresses: getaddrinfo',
                  'failed to open stream: Connection refused in'
                  'java.io.FileNotFoundException',
                  'java.net.ConnectException',
                  'java.net.UnknownHostException')

    def __init__(self):
        AuditPlugin.__init__(self)

        # Internal variables
        self._error_reported = False

        # User configured parameters
        self._listen_port = ports.REMOTEFILEINCLUDE
        self._listen_address = get_local_ip() or ''
        self._use_w3af_site = True

    def audit(self, freq):
        '''
        Tests an URL for remote file inclusion vulnerabilities.

        @param freq: A FuzzableRequest object
        '''
        # The plugin is going to use two different techniques:
        # 1- create a request that will include a file from the w3af site
        if self._use_w3af_site:
            self._w3af_site_test_inclusion(freq)

        # Sanity check
        if self._correctly_configured():
            # 2- create a request that will include a file from a local web server
            self._local_test_inclusion(freq)
        else:
            # Report error to the user only once
            if not self._error_reported:
                self._error_reported = True
                om.out.error(self.CONFIG_ERROR_MSG)

    def _correctly_configured(self):
        '''
        @return: True if the plugin is correctly configured to run.
        '''
        listen_address = self._listen_address
        listen_port = self._listen_port

        if listen_address and listen_port:
            with self._plugin_lock:
                # If we have an active instance then we're OK!
                if webserver.is_running(listen_address,
                                        listen_port):
                    return True

                # Test if it's possible to bind the address
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((listen_address, listen_port))
                except socket.error:
                    return False
                finally:
                    s.close()
                    del s
                return True

    def _local_test_inclusion(self, freq):
        '''
        Check for RFI using a local web server

        @param freq: A FuzzableRequest object
        @return: None, everything is saved to the kb
        '''
        #
        # The listen address is an empty string when I have no default route
        #
        # Only work if:
        #   - The listen address is private and the target address is private
        #   - The listen address is public and the target address is public
        #
        if self._listen_address == '':
            return

        is_listen_priv = is_private_site(self._listen_address)
        is_target_priv = is_private_site(freq.getURL().getDomain())

        if (is_listen_priv and is_target_priv) or \
                not (is_listen_priv or is_target_priv):
            om.out.debug(
                'RFI test using local web server for URL: ' + freq.getURL())
            om.out.debug('w3af is running a webserver')
            try:
                # Create file for remote inclusion
                php_jsp_code, rfi_data = self._create_file()

                # Setup the web server handler to return always the same response
                # body. This is important for the test, since it might be the case
                # that the web application prepends/appends something to the
                # URL being included, and we don't want to fail there!
                #
                # Also, this allows us to remove the payloads we sent with \0
                # which tried to achieve the same result.
                RFIWebHandler.RESPONSE_BODY = php_jsp_code

                # Start web server
                #
                # No real webroot is required since the custom handler returns
                # always the same HTTP response body
                webroot = '.'
                webserver.start_webserver(self._listen_address,
                                          self._listen_port, webroot,
                                          RFIWebHandler)

                # Perform the real work
                self._test_inclusion(freq, rfi_data)
            except Exception, e:
                om.out.error('An error occurred while running local webserver:'
                             ' "%s"' % e)

    def _w3af_site_test_inclusion(self, freq):
        '''
        Check for RFI using the official w3af site.

        @param freq: A FuzzableRequest object
        @return: None, everything is saved to the kb
        '''
        rfi_url = URL(self.RFI_TEST_URL)
        rfi_result = 'w3af by Andres Riancho'
        rfi_result_part_1 = 'w3af'
        rfi_result_part_2 = ' by Andres Riancho'

        rfi_data = RFIData(
            rfi_url, rfi_result_part_1, rfi_result_part_2, rfi_result)

        # Perform the real work
        self._test_inclusion(freq, rfi_data)

    def _test_inclusion(self, freq, rfi_data):
        '''
        Checks a FuzzableRequest for remote file inclusion bugs.

        @param freq: The fuzzable request that we want to inject into
        @param rfi_data: A RFIData object with all the information about the RFI
        @return: None, vulnerabilities are stored in the KB in _analyze_result
        '''
        orig_resp = self._uri_opener.send_mutant(freq)

        rfi_url_list = self._mutate_rfi_urls(rfi_data.rfi_url)
        mutants = create_mutants(freq, rfi_url_list, orig_resp=orig_resp)

        analyze_result_par = partial(self._analyze_result, rfi_data)

        self._send_mutants_in_threads(self._uri_opener.send_mutant,
                                      mutants,
                                      analyze_result_par)

    def _mutate_rfi_urls(self, orig_url):
        '''
        @param orig_url: url_object with the URL to mutate
        @return: A list of strings with URLs that will be sent to the remote
                 site to test if the inclusion is successful or not. Techniques
                 used to mutate:
                     * Remove protocol
                     * Case sensitive protocol
                     * Same as input
        '''
        result = []

        # same as input
        result.append(orig_url.url_string)

        # url without protocol
        url_str = orig_url.url_string.replace(
            orig_url.getProtocol() + '://', '', 1)
        result.append(url_str)

        # url without case insensitive protocol
        orig_proto = orig_url.getProtocol()
        mutated_proto = orig_proto.replace('http', 'hTtP')
        url_str = orig_url.url_string.replace(orig_proto, mutated_proto, 1)
        result.append(url_str)

        return result

    def _analyze_result(self, rfi_data, mutant, response):
        '''
        Analyze results of the _send_mutant method.
        '''
        if rfi_data.rfi_result in response:
            v = vuln.vuln(mutant)
            v.set_plugin_name(self.get_name())
            v.set_id(response.id)
            v.set_severity(severity.HIGH)
            v.set_name('Remote code execution')
            msg = 'A remote file inclusion vulnerability that allows remote' \
                  ' code execution was found at: ' + mutant.found_at()
            v.set_desc(msg)
            kb.kb.append_uniq(self, 'rfi', v)

        elif rfi_data.rfi_result_part_1 in response \
                and rfi_data.rfi_result_part_2 in response:
            # This means that both parts ARE in the response body but the
            # rfi_data.rfi_result is NOT in it. In other words, the remote
            # content was embedded but not executed
            v = vuln.vuln(mutant)
            v.set_plugin_name(self.get_name())
            v.set_id(response.id)
            v.set_severity(severity.MEDIUM)
            v.set_name('Remote file inclusion')
            msg = 'A remote file inclusion vulnerability without code' \
                  ' execution was found at: ' + mutant.found_at()
            v.set_desc(msg)
            kb.kb.append_uniq(self, 'rfi', v)

        else:
            #
            #   Analyze some errors that indicate that there is a RFI but
            #   with some "configuration problems"
            #
            for error in self.RFI_ERRORS:
                if error in response and not error in mutant.get_original_response_body():
                    v = vuln.vuln(mutant)
                    v.set_plugin_name(self.get_name())
                    v.set_id(response.id)
                    v.set_severity(severity.LOW)
                    v.addToHighlight(error)
                    v.set_name('Potential remote file inclusion')
                    msg = 'A potential remote file inclusion vulnerability' \
                          ' was identified by the means of application error' \
                          '  messages at: ' + mutant.found_at()
                    v.set_desc(msg)
                    kb.kb.append_uniq(self, 'rfi', v)
                    break

    def end(self):
        '''
        This method is called when the plugin wont be used anymore.
        '''
        self.print_uniq(kb.kb.get('rfi', 'rfi'), 'VAR')

    def _create_file(self):
        '''
        Create random name file php with random php content. To be used in the
        remote file inclusion test.

        @return: The file content to be served via the webserver.

        Please note that the generated code works both in PHP and JSP without
        any issues, since PHP will run everything between "<?" and "?>" and
        JSP will run code between "<%" and "%>".

        TODO: make this code compatible with: asp/aspx, jsp, js (nodejs), pl,
              py, rb, etc. Some code snippets that might help to achieve this
              task:

        asp_code = 'response.write("%s");\n response.write("%s");' % (
            rand1, rand2)
        asp_code = '<% \n '+asp_code+'\n %>'
        '''
        with self._plugin_lock:
            # First, generate the php file to be included.
            rfi_result_part_1 = rand1 = rand_alnum(9)
            rfi_result_part_2 = rand2 = rand_alnum(9)
            rfi_result = rand1 + rand2

            filename = rand_alnum(8)
            php_jsp_code = '<? echo "%s"; echo "%s"; ?>'
            php_jsp_code += '<%% out.print("%s"); out.print("%s"); %%>'
            php_jsp_code = php_jsp_code % (rand1, rand2, rand1, rand2)

            # Define the required parameters
            netloc = self._listen_address + ':' + str(self._listen_port)
            path = '/' + filename
            rfi_url = URL.from_parts('http', netloc, path, None, None, None)

            rfi_data = RFIData(
                rfi_url, rfi_result_part_1, rfi_result_part_2, rfi_result)

            return php_jsp_code, rfi_data

    def get_options(self):
        '''
        @return: A list of option objects for this plugin.
        '''
        ol = OptionList()

        d = 'IP address that the webserver will use to receive requests'
        h = 'w3af runs a webserver to serve the files to the target web application \
        when doing remote file inclusions. This setting configures where the webserver\
        is going to listen for requests.'
        o = opt_factory(
            'listen_address', self._listen_address, d, STRING, help=h)
        ol.add(o)

        d = 'TCP port that the webserver will use to receive requests'
        o = opt_factory('listen_port', self._listen_port, d, PORT)
        ol.add(o)

        d = 'Use w3af site to test for remote file inclusion'
        h = 'The plugin can use the w3af site to test for remote file inclusions, which is\
        convenient when you are performing a test behind a NAT firewall.'
        o = opt_factory('use_w3af_site', self._use_w3af_site, d, BOOL, help=h)
        ol.add(o)

        return ol

    def set_options(self, options_list):
        '''
        This method sets all the options that are configured using the user interface
        generated by the framework using the result of get_options().

        @param options_list: A dictionary with the options for the plugin.
        @return: No value is returned.
        '''
        self._listen_address = options_list['listen_address'].get_value()
        self._listen_port = options_list['listen_port'].get_value()
        self._use_w3af_site = options_list['use_w3af_site'].get_value()

        if not self._correctly_configured() and not self._use_w3af_site:
            raise w3afException(self.CONFIG_ERROR_MSG)

    def get_long_desc(self):
        '''
        @return: A DETAILED description of the plugin functions and features.
        '''
        return '''
        This plugin finds remote file inclusion vulnerabilities.

        Three configurable parameters exist:
            - listen_address
            - listen_port
            - use_w3af_site

        There are two ways of running this plugin, the most common one is to use
        w3af's site (w3af.sf.net) as the URL to include. This is convenient and
        requires zero configuration but leaks information about vulnerable sites
        to w3af.sf.net staff.

        The second way to configure this plugin runs a webserver on the box
        running w3af on the IP address and port specified by "listen_address"
        and "listen_port". This method requires the target web application to be
        able to contact the newly created server and will not work unless
        you also configure your NAT router and firewalls (if any exist).
        '''


class RFIWebHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    RESPONSE_BODY = None

    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self.RESPONSE_BODY)
        except Exception, e:
            om.out.debug('[RFIWebHandler] Exception: "%s".' % e)
        finally:
            # Clean up
            self.close_connection = 1
            self.rfile.close()
            self.wfile.close()
            return

    def log_message(self, fmt, *args):
        '''
        I dont want messages to be written to stderr, please ignore them.

        If I don't override this method I end up with messages like:
        eulogia.local - - [19/Oct/2012 10:12:33] "GET /GGC8s1dk HTTP/1.0" 200 -

        being printed to the console.
        '''
        pass


class RFIData(object):
    def __init__(self, rfi_url, rfi_result_part_1, rfi_result_part_2, rfi_result):
        self.rfi_url = rfi_url
        self.rfi_result_part_1 = rfi_result_part_1
        self.rfi_result_part_2 = rfi_result_part_2
        self.rfi_result = rfi_result
