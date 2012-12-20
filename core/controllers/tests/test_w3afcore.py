'''
test_w3afcore.py

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
import os
import shutil
import time
import unittest
import threading
import pprint

from multiprocessing.dummy import Process
from nose.plugins.attrib import attr

from core.controllers.w3afCore import w3afCore
from plugins.tests.helper import create_target_option_list


@attr('smoke')
class TestW3afCore(unittest.TestCase):

    def test_multiple_instances(self):
        '''Just making sure nothing crashes if I have more than 1 instance
        of w3afCore'''
        instances = []
        for _ in xrange(5):
            instances.append(w3afCore())

class TestW3afCorePause(unittest.TestCase):

    def setUp(self):
        '''
        This is a rather complex setUp since I need to move the count.py
        plugin to the plugin directory in order to be able to run it
        afterwards.

        In the tearDown method, I'll remove the file.
        '''
        self.src = os.path.join('core', 'controllers', 'tests', 'count.py')
        self.dst = os.path.join('plugins', 'crawl', 'count.py')
        shutil.copy(self.src, self.dst)

        self.w3afcore = w3afCore()
        
        target_opts = create_target_option_list('http://moth/')
        self.w3afcore.target.set_options(target_opts)

        self.w3afcore.plugins.set_plugins(['count',], 'crawl')

        # Verify env and start the scan
        self.w3afcore.plugins.init_plugins()
        self.w3afcore.verify_environment()
        
        self.count_plugin = self.w3afcore.plugins.plugins['crawl'][0]
        
    
    def tearDown(self):
        self.w3afcore.quit()
        
        # py and pyc file
        for fname in (self.dst, self.dst + 'c'):
            if os.path.exists(fname):
                os.remove(fname)
                
    def test_pause_unpause(self):
        '''
        Verify that the pause method actually works. In this case, working
        means that the process doesn't send any more HTTP requests, fact
        that is verified with the "fake" count plugin.
        '''        
        core_start = Process(target=self.w3afcore.start, name='TestRunner')
        core_start.daemon = True
        core_start.start()
        
        # Let the core start, and the count plugin send some requests.
        time.sleep(5)
        count_before_pause = self.count_plugin.count
        self.assertGreater(self.count_plugin.count, 0)
        
        # Pause and measure
        self.w3afcore.pause(True)
        count_after_pause = self.count_plugin.count
        
        time.sleep(2)
        count_after_sleep = self.count_plugin.count
        
        all_equal = count_before_pause == count_after_pause == count_after_sleep
        
        self.assertTrue(all_equal)

        # Unpause and verify that all requests were sent
        self.w3afcore.pause(False)
        core_start.join()
        
        self.assertEqual(self.count_plugin.count, self.count_plugin.loops)
    
    def test_pause_stop(self):
        '''
        Verify that the pause method actually works. In this case, working
        means that the process doesn't send any more HTTP requests after we,
        pause and that stop works when paused.
        '''
        core_start = Process(target=self.w3afcore.start, name='TestRunner')
        core_start.daemon = True
        core_start.start()
        
        # Let the core start, and the count plugin send some requests.
        time.sleep(5)
        count_before_pause = self.count_plugin.count
        self.assertGreater(self.count_plugin.count, 0)
        
        # Pause and measure
        self.w3afcore.pause(True)
        count_after_pause = self.count_plugin.count
        
        time.sleep(2)
        count_after_sleep = self.count_plugin.count
        
        all_equal = count_before_pause == count_after_pause == count_after_sleep
        
        self.assertTrue(all_equal)

        # Unpause and verify that all requests were sent
        self.w3afcore.stop()
        core_start.join()
        
        # No more requests sent after pause
        self.assertEqual(self.count_plugin.count, count_after_sleep)

    def test_stop(self):
        '''
        Verify that the stop method actually works. In this case, working
        means that the process doesn't send any more HTTP requests after we
        stop().
        '''
        core_start = Process(target=self.w3afcore.start, name='TestRunner')
        core_start.daemon = True
        core_start.start()
        
        # Let the core start, and the count plugin send some requests.
        time.sleep(5)
        count_before_stop = self.count_plugin.count
        self.assertGreater(count_before_stop, 0)
        
        # Stop now,
        self.w3afcore.stop()
        core_start.join()

        count_after_stop = self.count_plugin.count
        
        self.assertEqual(count_after_stop, count_before_stop)

        alive_threads = threading.enumerate()
        self.assertEqual(len(alive_threads), 0, nice_repr(alive_threads))

class TestExceptionHandler(TestW3afCorePause):
    '''
    Inherit from TestW3afCorePause to get the nice setUp().
    '''
    def test_same_id(self):
        '''
        Verify that the exception handler is the same before and after the scan
        '''
        before_id_ehandler = id(self.w3afcore.exception_handler)
        
        self.w3afcore.start()
        
        after_id_ehandler = id(self.w3afcore.exception_handler)
        
        self.assertEqual(before_id_ehandler, after_id_ehandler)
        


def nice_repr(alive_threads):
    repr_alive = [repr(x) for x in alive_threads]
    repr_alive.sort()
    return pprint.pformat(repr_alive)    