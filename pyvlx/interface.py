"""Module for interface to KLF 200."""
import json
import asyncio
import aiohttp
import async_timeout
import requests

from .exception import PyVLXException, InvalidToken


class Interface:
    """Interface to KLF 200."""

    def __init__(self, config):
        """Initialize interface class."""
        self.config = config
        self.token = None

    # pylint: disable=too-many-arguments
    def api_call(self, verb, action, params=None, add_authorization_token=True, retry=False):
        """Send api call."""
        if add_authorization_token and not self.token:
            self.refresh_token()

        try:
            return self._api_call_impl(verb, action, params, add_authorization_token)
        except InvalidToken:
            if not retry and add_authorization_token:
                self.refresh_token()
                # Recursive call of api_call
                return self.api_call(verb, action, params, add_authorization_token, True)
            else:
                raise

    def _api_call_impl(self, verb, action, params=None, add_authorization_token=True):
        url = self.create_api_url(self.config.host, verb)
        body = self.create_body(action, params)
        headers = self.create_headers(add_authorization_token, self.token)
        return self._do_http_request(url, body, headers)

    def _do_http_request(self, url, body, headers):
        try:
            return self._do_http_request_impl(url, body, headers)
        except asyncio.TimeoutError:
            raise PyVLXException("Request timeout when talking to VELUX API")
        except aiohttp.ClientError:
            raise PyVLXException("HTTP error when talking to VELUX API")
        except OSError:
            raise PyVLXException("OS error when talking to VELUX API")

    def _do_http_request_impl(self, url, body, headers):
        print(url, body, headers)

        r = requests.post(url, data=json.dumps(body), headers=headers, timeout=10)
        return json.loads(self.fix_response(r.text))

        
    def refresh_token(self):
        """Refresh API token from KLF 200."""
        json_response = self.api_call('auth', 'login', {'password': self.config.password}, add_authorization_token=False)
        if 'token' not in json_response:
            raise PyVLXException('no element token found in response: {0}'.format(json.dumps(json_response)))
        self.token = json_response['token']

    def disconnect(self):
        """Disconnect from KLF 200."""
        self.api_call('auth', 'logout', {}, add_authorization_token=True)
        self.token = None

    @staticmethod
    def create_api_url(host, verb):
        """Return full rest url."""
        return 'http://{0}/api/v1/{1}'.format(host, verb)

    @staticmethod
    def create_headers(add_authorization_token, token=None):
        """Create http header for rest request."""
        headers = {}
        headers['Content-Type'] = 'application/json'
        if add_authorization_token:
            headers['Authorization'] = 'Bearer ' + token
        return headers

    @staticmethod
    def create_body(action, params):
        """Create http body for rest request."""
        body = {}
        body['action'] = action
        if params is not None:
            body['params'] = params
        return body

    @staticmethod
    def evaluate_response(json_response):
        """Evaluate rest response."""
        if 'errors' in json_response and json_response['errors']:
            Interface.evaluate_errors(json_response)
        elif 'result' not in json_response:
            raise PyVLXException('no element result  found in response: {0}'.format(json.dumps(json_response)))
        elif not json_response['result']:
            raise PyVLXException('Request failed {0}'.format(json.dumps(json_response)))

    @staticmethod
    def evaluate_errors(json_response):
        """Evaluate rest errors."""
        if 'errors' not in json_response or \
           not isinstance(json_response['errors'], list) or \
           not json_response['errors'] or \
           not isinstance(json_response['errors'][0], int):
            raise PyVLXException('Could not evaluate errors {0}'.format(json.dumps(json_response)))

        # unclear if response may contain more errors than one. Taking the first.
        first_error = json_response['errors'][0]

        if first_error in [402, 403, 405, 406]:
            raise InvalidToken(first_error)

        raise PyVLXException('Unknown error code {0}'.format(first_error))

    @staticmethod
    def fix_response(response):
        """Fix broken rest reponses."""
        # WTF: For whatever reason, the KLF 200 sometimes puts an ')]}',' in front of the response ...
        index = response.find('{')
        if index > 0:
            return response[index:]
        return response
