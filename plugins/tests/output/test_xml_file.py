'''
test_xml_file.py

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
import StringIO

from lxml import etree
from nose.plugins.attrib import attr

import core.data.kb.vuln as vuln

from core.data.parsers.url import URL
from plugins.tests.helper import PluginTest, PluginConfig


@attr('smoke')
class TestXMLOutput(PluginTest):

    target_url = 'http://moth/w3af/audit/sql_injection/select/sql_injection_string.php'

    FILENAME = 'output-unittest.xml'
    XSD = os.path.join('plugins', 'output', 'xml_file', 'report.xsd')

    _run_configs = {
        'cfg': {
            'target': target_url + '?name=xxx',
            'plugins': {
                'audit': (PluginConfig('sqli'),),
                'crawl': (
                    PluginConfig(
                        'web_spider',
                        ('onlyForward', True, PluginConfig.BOOL)),
                ),
                'output': (
                    PluginConfig(
                        'xml_file',
                        ('output_file', FILENAME, PluginConfig.STR)),
                )
            },
        }
    }

    def test_found_vuln(self):
        cfg = self._run_configs['cfg']
        self._scan(cfg['target'], cfg['plugins'])

        kb_vulns = self.kb.get('sqli', 'sqli')
        file_vulns = self._from_xml_get_vulns()

        self.assertEqual(len(kb_vulns), 1, kb_vulns)

        self.assertEquals(
            set(sorted([v.get_url() for v in kb_vulns])),
            set(sorted([v.get_url() for v in file_vulns]))
        )

        self.assertEquals(
            set(sorted([v.get_name() for v in kb_vulns])),
            set(sorted([v.get_name() for v in file_vulns]))
        )

        self.assertEquals(
            set(sorted([v.get_plugin_name() for v in kb_vulns])),
            set(sorted([v.get_plugin_name() for v in file_vulns]))
        )

        self.assertEqual(validate_XML(file(self.FILENAME).read(), self.XSD),
                         '')

    def _from_xml_get_vulns(self):
        xp = XMLParser()
        parser = etree.XMLParser(target=xp)
        vulns = etree.fromstring(file(self.FILENAME).read(), parser)
        return vulns

    def tearDown(self):
        super(TestXMLOutput, self).tearDown()
        try:
            os.remove(self.FILENAME)
        except:
            pass


class XMLParser:
    vulns = []

    def start(self, tag, attrib):
        '''
        <vulnerability id="[87]" method="GET" name="Cross site scripting vulnerability"
                       plugin="xss" severity="Medium" url="http://moth/w3af/audit/xss/simple_xss_no_script_2.php"
                       var="text">
        '''
        if tag == 'vulnerability':
            v = vuln.vuln()
            v.set_plugin_name(attrib['plugin'])
            v.set_name(attrib['name'])
            v.set_url(URL(attrib['url']))
            self.vulns.append(v)

    def close(self):
        return self.vulns


def validate_XML(content, schema_content):
    '''
    Validate an XML against an XSD.

    @return: The validation error log as a string, an empty string is returned
             when there are no errors.
    '''
    xml_schema_doc = etree.parse(schema_content)
    xml_schema = etree.XMLSchema(xml_schema_doc)
    xml = etree.parse(StringIO.StringIO(content))

    # Validate the content against the schema.
    try:
        xml_schema.assertValid(xml)
    except etree.DocumentInvalid:
        return xml_schema.error_log

    return ''
