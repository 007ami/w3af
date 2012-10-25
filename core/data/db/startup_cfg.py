'''
startup_cfg.py

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
import ConfigParser

from datetime import datetime, date, timedelta

from core.controllers.misc.homeDir import get_home_dir


class StartUpConfig(object):
    '''
    Wrapper class for ConfigParser.ConfigParser.
    Holds the configuration for the VersionMgr update/commit process
    '''
    CFG_FILE = os.path.join(get_home_dir(), 'startup.conf')
    
    ISO_DATE_FMT = '%Y-%m-%d'
    # Frequency constants
    FREQ_DAILY = 'D' # [D]aily
    FREQ_WEEKLY = 'W' # [W]eekly
    FREQ_MONTHLY = 'M' # [M]onthly
    # DEFAULT VALUES
    DEFAULTS = {'auto-update': 'true', 'frequency': 'D',
                'last-update': 'None', 'last-rev': 0,
                'accepted-disclaimer': 'false'}

    def __init__(self, cfg_file=CFG_FILE):
        
        self._start_cfg_file = cfg_file
        self._start_section = 'STARTUP_CONFIG'
        
        self._config = ConfigParser.ConfigParser()
        configs = self._load_cfg()
        
        (self._autoupd, self._freq, self._lastupd, self._lastrev,
         self._accepted_disclaimer) = configs

    ### PROPERTIES #
    @property
    def last_upd(self):
        '''
        Getter method.
        '''
        return self._lastupd

    @last_upd.setter
    def last_upd(self, datevalue):
        '''
        @param datevalue: datetime.date value
        '''
        self._lastupd = datevalue
        self._config.set(self._start_section, 'last-update',
                         datevalue.isoformat())
    
    @property
    def accepted_disclaimer(self):
        return self._accepted_disclaimer

    @accepted_disclaimer.setter
    def accepted_disclaimer(self, accepted_decision):
        '''
        @param datevalue: datetime.date value
        '''
        self._accepted_disclaimer = accepted_decision
        value = 'true' if accepted_decision else 'false' 
        self._config.set(self._start_section, 'accepted-disclaimer',
                         value)
    
    @property
    def last_rev(self):
        return self._lastrev
    
    @last_rev.setter
    def last_rev(self, rev):
        self._lastrev = rev.number
        self._config.set(self._start_section, 'last-rev', self._lastrev)

    @property
    def freq(self):
        return self._freq

    @property
    def auto_upd(self):
        return self._autoupd

    ### METHODS #

    def _load_cfg(self):
        '''
        Loads configuration from config file.
        '''
        config = self._config
        startsection = self._start_section
        if not config.has_section(startsection):
            config.add_section(startsection)
            defaults = StartUpConfig.DEFAULTS
            config.set(startsection, 'auto-update', defaults['auto-update'])
            config.set(startsection, 'frequency', defaults['frequency'])
            config.set(startsection, 'last-update', defaults['last-update'])
            config.set(startsection, 'last-rev', defaults['last-rev'])
            config.set(startsection, 'accepted-disclaimer', defaults['accepted-disclaimer'])

        # Read from file
        config.read(self._start_cfg_file)

        boolvals = {'false': 0, 'off': 0, 'no': 0,
                    'true': 1, 'on': 1, 'yes': 1}

        auto_upd = config.get(startsection, 'auto-update', raw=True)
        auto_upd = bool(boolvals.get(auto_upd.lower(), False))

        accepted_disclaimer = config.get(startsection, 'accepted-disclaimer', raw=True)
        accepted_disclaimer = bool(boolvals.get(accepted_disclaimer.lower(), False))

        freq = config.get(startsection, 'frequency', raw=True).upper()
        if freq not in (StartUpConfig.FREQ_DAILY, StartUpConfig.FREQ_WEEKLY,
                        StartUpConfig.FREQ_MONTHLY):
            freq = StartUpConfig.FREQ_DAILY

        lastupdstr = config.get(startsection, 'last-update', raw=True).upper()
        # Try to parse it
        try:
            lastupd = datetime.strptime(lastupdstr, self.ISO_DATE_FMT).date()
        except:
            # Provide default value that enforces the update to happen
            lastupd = date.today() - timedelta(days=31)
        try:
            lastrev = config.getint(startsection, 'last-rev')
        except TypeError:
            lastrev = 0
        return (auto_upd, freq, lastupd, lastrev, accepted_disclaimer)

    def save(self):
        '''
        Saves current values to cfg file
        '''
        with open(self._start_cfg_file, 'wb') as configfile:
            self._config.write(configfile)
