'''
helper.py

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
import os
import sys
import unittest

from mock import MagicMock


class mock_stdout(object):
    def __init__(self):
        self.messages = []
    
    def write(self, msg):
        self.messages.extend( msg.split('\n\r') )
    
    flush = MagicMock()
    
    def clear(self):
        self.messages = []


class ConsoleTestHelper(unittest.TestCase):
    '''
    Helper class to build console UI tests.
    '''
    
    OUTPUT_FILE = 'output-w3af-unittest.txt'
    OUTPUT_HTTP_FILE = 'output-w3af-unittest-http.txt'
    
    def setUp(self):
        self.mock_sys()
        
    def tearDown(self):
        #sys.exit.assert_called_once_with(0)        
        self.restore_sys()
        self._mock_stdout.clear()
        
        for fname in (self.OUTPUT_FILE, self.OUTPUT_HTTP_FILE):
            if os.path.exists(fname):
                os.remove(fname)

    def mock_sys(self):
        # backup
        self.old_stdout = sys.stdout
        self.old_exit = sys.exit
        
        # assign new
        self._mock_stdout = mock_stdout()
        sys.stdout = self._mock_stdout
        sys.exit = MagicMock()

    def restore_sys(self):
        sys.stdout = self.old_stdout
        sys.exit = self.old_exit
        
    def startswith_expected_in_output(self, expected):
        for line in expected:
            for sys_line in self._mock_stdout.messages:
                if sys_line.startswith(line):
                    break
            else:
                return False
        else:
            return True
            
    def all_expected_in_output(self, expected):
        for line in expected:
            if line not in self._mock_stdout.messages:
                return False
        else:
            return True
    
    def error_in_output(self, errors):
        for line in self._mock_stdout.messages:
            for error_str in errors:
                if error_str in line:
                    return True
        
        return False
        