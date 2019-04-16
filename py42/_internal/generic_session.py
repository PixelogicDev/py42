import threading
import traceback
from urlparse import urljoin, urlparse

import requests.adapters

import py42.debug as debug
import py42.debug_level as debug_level
import py42.settings as settings
import py42.util as util


class Session(requests.Session):

    def __init__(self, host_address, auth_handler=None):
        super(Session, self).__init__()
        if not host_address.startswith("http://") and not host_address.startswith("https://"):
            host_address = "https://{0}".format(host_address)

        self._host_address = host_address
        self._exception_message_handler = settings.global_exception_message_handler
        self._auth_handler = auth_handler
        self._valid_auth = self._auth_handler is None
        self._max_tries = 2
        self._auth_lock = threading.Lock()

        adapter = requests.adapters.HTTPAdapter(pool_connections=500, pool_maxsize=500)
        self.mount("https://", adapter)
        self.mount("http://", adapter)

        parsed_host = urlparse(self._host_address)
        host = parsed_host.netloc

        self.proxies = settings.proxies
        self.verify = settings.verify_ssl_certs
        self.headers = {"Accept": "application/json",
                        "Content-Type": "application/json",
                        "Host": host,
                        "Accept-Encoding": "gzip, deflate",
                        "Connection": "keep-alive"}

    @property
    def host_address(self):
        return self._host_address

    def request(self, method, url, params=None, data=None, headers=None, cookies=None, files=None, auth=None,
                timeout=None, allow_redirects=True, proxies=None, hooks=None, stream=None, verify=None, cert=None,
                json=None, force_sync=None, then=None, catch=None):
        try:
            url = urljoin(self._host_address, url)
            times_try = 0
            response = None
            while times_try < self._max_tries:
                self._add_auth_if_missing()
                try:

                    if debug.will_print_for(debug_level.INFO):
                        self._print_request(method, url, params=params, data=data)

                    response = super(Session, self).request(method, url,
                                                            params=params,
                                                            data=data,
                                                            headers=headers,
                                                            cookies=cookies,
                                                            files=files,
                                                            auth=auth,
                                                            timeout=timeout,
                                                            allow_redirects=allow_redirects,
                                                            proxies=proxies,
                                                            hooks=hooks,
                                                            stream=stream,
                                                            verify=verify,
                                                            cert=cert)

                except requests.RequestException as e:
                    trace = traceback.format_exc()
                    self._handle_error(e, trace, catch)
                    return

                times_try += 1
                handler = self._auth_handler
                no_auth = handler is not None and handler.response_indicates_unauthorized(response)
                if no_auth and times_try < self._max_tries:
                    self._valid_auth = False
                    continue
                else:
                    status_code = response.status_code
                    should_raise = status_code >= 400
                    if (times_try >= self._max_tries and no_auth) or should_raise:
                        try:
                            response.raise_for_status()
                        except requests.HTTPError as e:
                            trace = traceback.format_exc()
                            self._handle_error(e, trace, catch)
                            return
                    else:
                        # only call the user-supplied "then" callback if the request had a success status code.
                        break

            if then is not None and response is not None:
                try:
                    then(response)
                except Exception as e:
                    trace = traceback.format_exc()
                    self._handle_error(e, trace, catch)
                    return

            return response

        except Exception as e:
            trace = traceback.format_exc()
            self._handle_error(e, trace, catch)
            return

    def _add_auth_if_missing(self):
        if self._auth_handler is not None and not self._valid_auth:
            try:
                self._auth_lock.acquire()
                if not self._valid_auth:
                    self._auth_handler.handle_unauthorized(self)
                    self._valid_auth = True
            finally:
                self._auth_lock.release()

    def _handle_error(self, exception, exception_trace, request_handler):
        if request_handler is not None:
            request_handler(exception)
        else:
            # log unhandled exceptions
            if self._exception_message_handler is not None:
                self._exception_message_handler(exception_trace)
            # always raise unhandled exceptions when using a synchronous client
            raise exception

    def _print_request(self, method, url, params=None, data=None):
        print("{0}{1}".format(str(method).ljust(8), url))
        if debug.will_print_for(debug_level.TRACE):
            if self.headers:
                util.print_dict(self.headers, "  headers")
        if debug.will_print_for(debug_level.DEBUG):
            if params:
                util.print_dict(params, "  params")
            if data:
                util.print_dict(data, "  data")
