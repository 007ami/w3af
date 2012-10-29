'''
dogtail_unittest.py

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
import getpass
import time

from core.ui.gui.tests.dogtail_wrapper.utils import (set_display_to_self,
                                                     restore_original_display)
from core.ui.gui.tests.dogtail_wrapper.gnome import Gnome


class dummy():
    pass


class DogtailUnittest(unittest.TestCase):
    '''
    My GUI unittests will inherit from this class, which will basically start the
    X server in order to have all tests run in headless mode.
    '''
    def __init__(self, methodName='runTest'):
        '''
        One of the most important tricks for being able to run dogtail tests via
        nosetests without any special parameters is done in this __init__ method.
        
        The thing I found is that when importing dogtail modules, they are going
        to "hook" to the display that is set to the current environment at
        import time; not use time. In other words, this will work as expected:
        
            os.environ['DISPLAY'] = ':9'
            from dogtail import tree
            ...
            tree()
            ...
        
        This is NOT going to work as expected:
        
            from dogtail import tree
            ...
            os.environ['DISPLAY'] = ':9'
            tree()
            ...
        
        And this is not working either:
        
            os.environ['DISPLAY'] = ':9'
            from dogtail import tree
            ...
            os.environ['DISPLAY'] = ':0'
            tree()
            ...
        
        So, I import stuff here and store a reference as an object attribute
        in order to be able to use it in all the remaining tests.
        
        The only issue that comes with this is that not more that one DISPLAY
        can be used at the same time for testing with dogtail.
        
        The second trick that was discovered during my testing is that when
        importing dogtail the display NEEDS to point to a working X environment
        with a11y enabled. That's why you'll see this before the imports:
        
            self.gnome = Gnome()
            self.gnome.start_sync()
         
        '''
        unittest.TestCase.__init__(self, methodName=methodName)
        
        self.gnome = Gnome()
        self.gnome.start_sync()
        set_display_to_self()
        
        from dogtail import tree
        from dogtail.utils import run
        from dogtail.rawinput import pressKey
        from dogtail.predicate import GenericPredicate
        
        self.dogtail = dummy()
        self.dogtail.utils = dummy()
        self.dogtail.predicate = dummy()
        self.dogtail.rawinput = dummy()
        
        self.dogtail.tree = tree
        self.dogtail.utils.run = run
        self.dogtail.predicate.GenericPredicate = GenericPredicate
        self.dogtail.rawinput.pressKey = pressKey
        
        # I don't care about Gnome anymore, I just started it for giving dogtail
        # a suitable environment to run. I'll start and stop new Gnome instances
        # in setUp and tearDown
        self.gnome.stop()

    def setUp(self):
        time.sleep(5)
        set_display_to_self()
        self.gnome = Gnome()
        self.gnome.start_sync()
    
    def tearDown(self):
        self.gnome.stop()
        restore_original_display()

    def logout(self):
        '''
        Logs out the full gnome session. Be sure to have your documents saved,
        as running may cause loosing the changes, or it may halt the logout
        process.
        ''' 
        # A gnome-shell object
        shell = self.dogtail.tree.root.application('gnome-shell')
        # Click onto a super menu label that we find under the g-s top panel object.
        # We need these indexes as g-s a11y support is a wee bit messy.
        shell[0][1][2].child(getpass.getuser(), roleName='label').click()
        # We can child this all the way down from the app as there's no other Log Out... label
        shell.child('Log Out...', roleName='label').click()
        # This takes care of the 60 second dialog.
        # Sometimes a dialog warning about unsaved work in gedit etc. pops out, but that has the same
        # push button in which case this will take care of that dialog. If another dialog pops-out
        # in the affected application however, that might put the logout process on hold again. Unfortunatelly
        # we cannot do anything about that with dotail at that point as a11y registry got disabled already
        # by the logout process.
        shell[0][1].child(roleName='dialog', recursive=False).child('Log Out', roleName='push button').click()
        
        # Give the session some time to end before we kill it.
        time.sleep(10)
