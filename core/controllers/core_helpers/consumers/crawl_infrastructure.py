'''
crawl_infrastructure.py

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
import Queue

import core.controllers.output_manager as om
import core.data.kb.config as cf


from core.controllers.core_helpers.consumers.base_consumer import BaseConsumer
from core.controllers.core_helpers.consumers.constants import POISON_PILL
from core.controllers.exceptions import w3afException, w3afRunOnce
from core.controllers.threads.threadpool import return_args
from core.controllers.core_helpers.update_urls_in_kb import (update_kb,
                                                             get_urls_from_kb,
                                                             get_fuzzable_requests_from_kb)
from core.data.db.variant_db import VariantDB
from core.data.bloomfilter.scalable_bloom import ScalableBloomFilter


class crawl_infrastructure(BaseConsumer):
    '''
    Consumer thread that takes fuzzable requests from the input Queue that is
    seeded by the core, sends each fr to all crawl and infrastructure plugins,
    get()'s the output from those plugins and puts them in the input Queue
    again for continuing with the discovery process.
    '''

    def __init__(self, crawl_infrastructure_plugins, w3af_core,
                 max_discovery_time):
        '''
        @param in_queue: The input queue that will feed the crawl_infrastructure plugins
        @param crawl_infrastructure_plugins: Instances of crawl_infrastructure plugins in a list
        @param w3af_core: The w3af core that we'll use for status reporting
        @param max_discovery_time: The max time (in seconds) to use for the discovery phase
        '''
        super(
            crawl_infrastructure, self).__init__(crawl_infrastructure_plugins, w3af_core,
                                                 thread_name='CrawlInfra')
        self._max_discovery_time = max_discovery_time

        # For filtering fuzzable requests found by plugins:
        self._variant_db = VariantDB()
        self._already_seen_urls = ScalableBloomFilter()

        self._disabled_plugins = set()

    def run(self):
        '''
        Consume the queue items, sending them to the plugins which are then going
        to find vulnerabilities, new URLs, etc.

        TODO: Report progress to w3afCore somehow.
        '''

        while True:

            try:
                work_unit = self.in_queue.get(timeout=0.2)
            except:
                pass
            else:
                if work_unit == POISON_PILL:

                    # Close the pool and wait for everyone to finish
                    self._threadpool.close()
                    self._threadpool.join()

                    self._teardown()

                    # Finish this consumer and everyone consuming the output
                    self._out_queue.put(POISON_PILL)
                    self.in_queue.task_done()
                    break

                else:

                    self._consume(work_unit)
                    self.in_queue.task_done()
            finally:
                self._route_all_plugin_results()

    def _teardown(self, plugin=None):
        '''End plugins'''
        if plugin is None:
            to_teardown = self._consumer_plugins
        else:
            to_teardown = [plugin, ]

        for plugin in to_teardown:
            try:
                plugin.end()
            except w3afException, e:
                om.out.error('The plugin "%s" raised an exception in the '
                             'end() method: %s' % (plugin.get_name(), e))

    def _consume(self, work_unit):
        for plugin in self._consumer_plugins:

            if plugin in self._disabled_plugins:
                continue

            om.out.debug('%s plugin is testing: "%s"' % (
                plugin.get_name(), work_unit))


            # TODO: unittest what happens if an exception (which is not handled
            #       by the exception handler) is raised. Who's doing a .get()
            #       on those ApplyResults generated here?
            self._threadpool.apply_async(return_args(self._discover_worker),
                                        (plugin, work_unit,),
                                         callback=self._plugin_finished_cb)
            self._route_all_plugin_results()

    def _plugin_finished_cb(self, ((plugin, fuzzable_request), plugin_result)):
        self._route_plugin_results(plugin)

        # Finished one fuzzable_request, inc!
        self._w3af_core.progress.inc()

    def _route_all_plugin_results(self):
        for plugin in self._consumer_plugins:

            if plugin in self._disabled_plugins:
                continue

            self._route_plugin_results(plugin)

    def _route_plugin_results(self, plugin):
        '''
        Retrieve the results from all plugins and put them in our output Queue.
        '''
        while True:

            try:
                fuzzable_request = plugin.output_queue.get_nowait()
            except Queue.Empty:
                break
            else:
                # The plugin has finished and now we need to analyze which of
                # the returned fuzzable_request_list are new and should be put in the
                # input_queue again.
                if self._is_new_fuzzable_request(plugin, fuzzable_request):

                    # Update the list / set that lives in the KB
                    update_kb(fuzzable_request)

                    self._out_queue.put(
                        (plugin.get_name(), None, fuzzable_request))

    def join(self):
        super(crawl_infrastructure, self).join()
        self.cleanup()
        self.show_summary()

    def terminate(self):
        super(crawl_infrastructure, self).terminate()
        self.cleanup()
        self.show_summary()

    def cleanup(self):
        '''Remove the crawl and bruteforce plugins from memory.'''
        self._w3af_core.plugins.plugins['crawl'] = []
        self._w3af_core.plugins.plugins['infrastructure'] = []

        self._disabled_plugins = set()
        self._consumer_plugins = []

    def show_summary(self):
        '''
        This method is called after the crawl and bruteforce phases finishes and
        reports identified URLs and fuzzable requests to the user.
        '''
        if not get_fuzzable_requests_from_kb():
            om.out.information('No URLs found during crawl phase.')
            return

        # Sort URLs
        tmp_url_list = get_urls_from_kb()[:]
        tmp_url_list = list(set(tmp_url_list))
        tmp_url_list.sort()

        msg = 'Found %s URLs and %s different points of injection.'
        msg = msg % (len(tmp_url_list), len(get_fuzzable_requests_from_kb()))
        om.out.information(msg)

        # print the URLs
        om.out.information('The list of URLs is:')
        for i in tmp_url_list:
            om.out.information('- ' + i)

        # Now I simply print the list that I have after the filter.
        tmp_fr = ['- ' + str(fr) for fr in get_fuzzable_requests_from_kb()]
        tmp_fr.sort()

        om.out.information('The list of fuzzable requests is:')
        map(om.out.information, tmp_fr)

    def _should_stop_discovery(self):
        '''
        @return: True if we should stop the crawl phase because of time limit
                 set by the user, or simply because the user wants to stop the
                 crawl phase.
        '''
        # If the user wants to stop, I have to stop and at least
        # return the findings I've got until now.
        if self._w3af_core.status.is_stopped():
            return True

        # TODO: unittest this limit
        if self._w3af_core.get_run_time() > self._max_discovery_time:
            om.out.information('Maximum crawl time limit hit.')
            return True

        return False

    def _remove_discovery_plugin(self, plugin_to_remove):
        '''
        Remove plugins that don't want to be run anymore and raised a w3afRunOnce
        exception during the crawl phase.
        '''
        for plugin_type in ('crawl', 'infrastructure'):
            if plugin_to_remove in self._w3af_core.plugins.plugins[plugin_type]:

                msg = 'The %s plugin: "%s" wont be run anymore.'
                om.out.debug(
                    msg % (plugin_type, plugin_to_remove.get_name()))

                # Add it to the list of disabled plugins, and run the end() method
                self._disabled_plugins.add(plugin_to_remove)
                self._teardown(plugin_to_remove)

                # TODO: unittest that they are really disabled after adding them
                #       to the disabled_plugins set.

                break

    def _is_new_fuzzable_request(self, plugin, fuzzable_request):
        '''
        @param plugin: The plugin that found these fuzzable requests

        @param fuzzable_request: A potentially new fuzzable request

        @return: True if @FuzzableRequest is new (never seen before).
        '''
        base_urls_cf = cf.cf.get('baseURLs')

        fr_uri = fuzzable_request.get_uri()
        # No need to care about fragments
        # (http://a.com/foo.php#frag). Remove them
        fuzzable_request.set_uri(fr_uri.remove_fragment())

        if fr_uri.base_url() in base_urls_cf:
            # Filter out the fuzzable requests that aren't important
            # (and will be ignored by audit plugins anyway...)
            #
            #   What I want to do here, is filter the repeated fuzzable requests.
            #   For example, if the spidering process found:
            #       - http://host.tld/?id=3739286
            #       - http://host.tld/?id=3739285
            #       - http://host.tld/?id=3739282
            #       - http://host.tld/?id=3739212
            #
            #   I don't want to have all these different fuzzable requests. The reason is that
            #   audit plugins will try to send the payload to each parameter, thus generating
            #   the following requests:
            #       - http://host.tld/?id=payload1
            #       - http://host.tld/?id=payload1
            #       - http://host.tld/?id=payload1
            #       - http://host.tld/?id=payload1
            #
            #   w3af has a cache, but its still a waste of time to send those requests.
            #
            #   Now lets analyze this with more than one parameter. Spidered URIs:
            #       - http://host.tld/?id=3739286&action=create
            #       - http://host.tld/?id=3739285&action=create
            #       - http://host.tld/?id=3739282&action=remove
            #       - http://host.tld/?id=3739212&action=remove
            #
            #   Generated requests:
            #       - http://host.tld/?id=payload1&action=create
            #       - http://host.tld/?id=3739286&action=payload1
            #       - http://host.tld/?id=payload1&action=create
            #       - http://host.tld/?id=3739285&action=payload1
            #       - http://host.tld/?id=payload1&action=remove
            #       - http://host.tld/?id=3739282&action=payload1
            #       - http://host.tld/?id=payload1&action=remove
            #       - http://host.tld/?id=3739212&action=payload1
            #
            #   In cases like this one, I'm sending these repeated requests:
            #       - http://host.tld/?id=payload1&action=create
            #       - http://host.tld/?id=payload1&action=create
            #       - http://host.tld/?id=payload1&action=remove
            #       - http://host.tld/?id=payload1&action=remove
            #
            if fr_uri in self._already_seen_urls:
                return False
            else:
                self._already_seen_urls.add(fr_uri)

                if self._variant_db.need_more_variants(fr_uri):
                    self._variant_db.append(fr_uri)

                    msg = 'New URL found by %s plugin: "%s"' % (plugin.get_name(),
                                                                fuzzable_request.get_url())
                    om.out.information(msg)
                    return True

        return False

    def _discover_worker(self, plugin, fuzzable_request):
        '''
        This method runs @plugin with FuzzableRequest as parameter and returns
        new fuzzable requests and/or stores vulnerabilities in the knowledge base.

        Since threadpool's apply_async runs the callback only when the call to
        this method ends without any exceptions, it is *very important* to handle
        exceptions correctly here. Failure to do so will end up in _task_done not
        called, which will make has_pending_work always return True.

        Python 3 has an error_callback in the apply_async method, which we could
        use in the future.

        TODO: unit-test this method

        @return: A list with the newly found fuzzable requests.
        '''
        # Please note that I add a task to self, this task is marked as DONE
        # in the finally clause below
        self._add_task()
        
        om.out.debug('Called _discover_worker(%s,%s)' % (plugin.get_name(),
                                                         fuzzable_request.get_uri()))

        # Should I continue with the crawl phase? If not, return an empty result
        if self._should_stop_discovery():
            return []

        # Status reporting
        status = self._w3af_core.status
        status.set_phase('crawl')
        status.set_running_plugin(plugin.get_name())
        status.set_current_fuzzable_request(fuzzable_request)
        om.out.debug('%s is testing "%s"' % (plugin.get_name(),
                     fuzzable_request.get_uri()))

        try:
            result = plugin.discover_wrapper(fuzzable_request)
        except KeyboardInterrupt:
            # TODO: Is this still working? How do we handle Ctrl+C in a thread?
            om.out.information('The user interrupted the crawl phase, '
                               'continuing with audit.')
        except w3afException, e:
            msg = 'An exception was found while running "%s" with "%s": "%s".'
            om.out.error(msg % (plugin.get_name(), fuzzable_request), e)
        except w3afRunOnce:
            # Some plugins are meant to be run only once
            # that is implemented by raising a w3afRunOnce
            # exception
            self._remove_discovery_plugin(plugin)
        except Exception, e:
            self.handle_exception(plugin.get_type(), plugin.get_name(),
                                  fuzzable_request, e)

        else:
            # The plugin output is retrieved and analyzed by the
            # _route_plugin_results method, here we just verify that the plugin
            # result is None (which proves that the plugin respects this part
            # of the API)
            if result is not None:
                msg = 'The %s plugin did NOT return None.' % plugin.get_name()
                ve = ValueError(msg)
                self.handle_exception(plugin.get_type(), plugin.get_name(),
                                      fuzzable_request, ve)
        
        finally:
            self._task_done(None)
