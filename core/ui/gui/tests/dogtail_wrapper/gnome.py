'''
gnome.py

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
import tempfile

from core.ui.gui.tests.dogtail_wrapper.xvfb_server import XVFBServer, DISPLAY 


class Gnome(XVFBServer):
    '''
    This class runs all the required commands to have a working Gnome
    environment within a Xvfb; which is required to be able to have a11y
    features, which are needed for LDTP to work.
    
    Lots of tricks seen in this code were taken from mago's documentation
    on how to run Mago on Hudson and from dogtail's run headless script:
    
        * http://mago.ubuntu.com/Documentation/RunningOnHudson
        * https://fedorahosted.org/dogtail/browser/scripts/dogtail-run-headless?rev=099577f6152ebd229eae530fff6b2221f72f05ae
        * https://fedorahosted.org/dogtail/browser/scripts/dogtail-run-headless
    '''
    XINITRC = os.path.join( os.getcwd(), 'core', 'ui', 'gui', 'tests',
                            'dogtail_wrapper', 'dogtail.xinitrc')
    
    START_CMD = 'xinit %s -- %s %s -screen 0 %sx%sx16 -ac -noreset -shmem -fbdir %s'
    START_CMD = START_CMD % (XINITRC, XVFBServer.XVFB_BIN, DISPLAY,
                             XVFBServer.WIDTH, XVFBServer.HEIGTH,
                             tempfile.gettempdir())

    
    