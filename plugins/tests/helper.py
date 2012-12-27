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
import unittest
import urllib2

from nose.plugins.skip import SkipTest
from nose.plugins.attrib import attr

import core.data.kb.knowledge_base as kb

from core.controllers.w3afCore import w3afCore
from core.controllers.misc.homeDir import W3AF_LOCAL_PATH
from core.controllers.misc.decorators import retry

from core.data.options.opt_factory import opt_factory
from core.data.options.option_types import LIST
from core.data.options.option_list import OptionList

os.chdir(W3AF_LOCAL_PATH)


class PluginTest(unittest.TestCase):
    '''
    Remember that nosetests can't find test generators in unittest.TestCase,
    see http://stackoverflow.com/questions/6689537/nose-test-generators-inside-class ,
    '''

    runconfig = {}
    kb = kb.kb

    def setUp(self):
        self.kb.cleanup()
        self.w3afcore = w3afCore()

    def tearDown(self):
        self.w3afcore.quit()
        self.kb.cleanup()

    @retry(tries=3, delay=0.5, backoff=2)
    def _verify_targets_up(self, target_list):
        for target in target_list:
            msg = 'The target site "%s" is down' % target
            
            try:
                response = urllib2.urlopen(target)
                response.read()
            except urllib2.URLError, e:
                if hasattr(e, 'code') and e.code == 404:
                    continue
                
                self.assertTrue(False, msg)
            
            except Exception, e:
                self.assertTrue(False, msg)

    def _scan(self, target, plugins, debug=False, assert_exceptions=True,
              verify_targets=True):
        '''
        Setup env and start scan. Typically called from children's
        test methods.

        @param target: The target to scan.
        @param plugins: PluginConfig objects to activate and setup before
            the test runs.
        '''
        if not isinstance(target, (basestring, tuple)):
            raise TypeError('Expected basestring or tuple in scan target.')
        
        if isinstance(target, basestring):
            target = (target,)
        
        if verify_targets:
            self._verify_targets_up(target)
        
        target_opts = create_target_option_list(*target)
        self.w3afcore.target.set_options(target_opts)

        # Enable plugins to be tested
        for ptype, plugincfgs in plugins.items():
            self.w3afcore.plugins.set_plugins(
                [p.name for p in plugincfgs], ptype)

            for pcfg in plugincfgs:
                plugin_instance = self.w3afcore.plugins.get_plugin_inst(
                    ptype, pcfg.name)
                default_option_list = plugin_instance.get_options()
                unit_test_options = pcfg.options
                for option in default_option_list:
                    if option.get_name() not in unit_test_options:
                        unit_test_options.add(option)

                self.w3afcore.plugins.set_plugin_options(
                    ptype, pcfg.name, unit_test_options)

        # Enable text output plugin for debugging
        if debug:
            self.w3afcore.plugins.set_plugins(['text_file', ], 'output')

        # Verify env and start the scan
        self.w3afcore.plugins.init_plugins()
        self.w3afcore.verify_environment()
        self.w3afcore.start()

        #
        # I want to make sure that we don't have *any hidden* exceptions in our
        # tests. This was in tearDown before, but moved here because I was getting
        # failed assertions in my test code that were because of exceptions in the
        # scan and they were hidden.
        #
        if assert_exceptions:
            caught_exceptions = self.w3afcore.exception_handler.get_all_exceptions()
            msg = [e.get_summary() for e in caught_exceptions]
            self.assertEqual(len(caught_exceptions), 0, msg)

class PluginConfig(object):

    BOOL = 'boolean'
    STR = 'string'
    LIST = 'list'
    INT = 'integer'
    URL = 'url'

    def __init__(self, name, *opts):
        self._name = name
        self._options = OptionList()
        for optname, optval, optty in opts:
            self._options.append(opt_factory(optname, str(optval), '', optty))

    @property
    def name(self):
        return self._name

    @property
    def options(self):
        return self._options


@attr('root')
def onlyroot(meth):
    '''
    Function to decorate tests that should be called as root.

    Raises a nose SkipTest exception if the user doesn't have root permissions.
    '''
    def test_inner_onlyroot(self, *args, **kwds):
        '''Note that this method needs to start with test_ in order for nose
        to run it!'''
        if os.geteuid() == 0 or os.getuid() == 0:
            return meth(self, *args, **kwds)
        else:
            raise SkipTest('This test requires root privileges.')
    test_inner_onlyroot.root = True
    return test_inner_onlyroot


def create_target_option_list(*target):
    opts = OptionList()

    opt = opt_factory('target', '', '', LIST)
    opt.set_value(','.join(target))
    opts.add(opt)
    
    opt = opt_factory('target_os', ('unknown', 'unix', 'windows'), '', 'combo')
    opts.add(opt)
    
    opt = opt_factory('target_framework',
                      ('unknown', 'php', 'asp', 'asp.net',
                       'java', 'jsp', 'cfm', 'ruby', 'perl'),
                      '', 'combo'
    )
    opts.add(opt)
    
    return opts