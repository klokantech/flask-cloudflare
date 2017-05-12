from flask import _app_ctx_stack, json
from requests import Request, Session


class CloudFlare:

    """CloudFlare API integration for Flask.

        cloudflare = CloudFlare(app)

        zone = cloudflare.api.get('zones').filter(name='example.org').first()
        cloudflare.api.put('zones', zone['id']).values(paused=True).execute()
    """

    def __init__(self, app=None):
        self.auth_email = None
        self.auth_key = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the extension.

        To authenticate with CloudFlare API, configure the
        CLOUDFLARE_AUTH_EMAIL and CLOUDFLARE_AUTH_KEY options.
        """
        app.extensions['cloudflare'] = self
        self.auth_email = app.config['CLOUDFLARE_AUTH_EMAIL']
        self.auth_key = app.config['CLOUDFLARE_AUTH_KEY']

    @property
    def api(self):
        """Return API interface for the current Flask application context."""
        ctx = _app_ctx_stack.top
        api = getattr(ctx, 'cloudflare_api', None)
        if api is None:
            api = ctx.api = API(self.session())
        return api

    def session(self):
        """Return new HTTP session for communication with the API."""
        session = Session()
        session.headers['X-Auth-Email'] = self.auth_email
        session.headers['X-Auth-Key'] = self.auth_key
        session.timeout = 20
        return session


class API:

    """API interface.

    Wraps GET, POST, PUT and DELETE operations with methods that
    return query objects. The list of arguments to these methods
    represents the path to the queried endpoint.

        api.get('zones', 'ABC', 'dns_records') => GET /zones/ABC/dns_records
    """

    def __init__(self, session):
        self.session = session

    def get(self, *args):
        """Return GET query."""
        return APIQuery(self.session, self.request('GET', args))

    def post(self, *args):
        """Return POST query."""
        return APIQuery(self.session, self.request('POST', args))

    def put(self, *args):
        """Return PUT query."""
        return APIQuery(self.session, self.request('PUT', args))

    def delete(self, *args):
        """Return DELETE query."""
        return APIQuery(self.session, self.request('DELETE', args))

    def request(self, method, path):
        """Return HTTP request for given method and endpoint path."""
        url = 'https://api.cloudflare.com/client/v4/' + '/'.join(path)
        return Request(method, url)


class APIQuery:

    """API query.

    Use filter() and values() to provide parameters; then first(),
    all(), execute() or __iter__() to actually perform the query and
    return results. Note that DELETE queries don't return anything.

    Paging is handled transparently by all() and __iter__().

    API errors are translated into APIError exceptions.
    """

    def __init__(self, session, request):
        self.session = session
        self.request = request
        self.payload = {}

    def filter(self, **kwargs):
        """Add parameters to GET request."""
        assert self.request.method == 'GET'
        self.request.params.update(kwargs)
        return self

    def values(self, **kwargs):
        """Add items to POST or PUT request JSON body."""
        assert self.request.method in {'POST', 'PUT'}
        self.payload.update(kwargs)
        return self

    def first(self):
        """Perform query and return the first result."""
        return next(iter(self), None)

    def all(self):
        """Perform query and return all results in a list."""
        return list(self)

    def execute(self):
        """Perform query without returning results."""
        self.send()

    def __iter__(self):
        """Perform query and iterate through all results."""
        while True:
            data = self.send()
            result = data['result']
            if isinstance(result, dict):
                yield result
                break
            yield from result
            info = data.get('result_info')
            if info is None:
                break
            assert self.request.method == 'GET'
            if info['count'] < info['per_page']:
                break
            self.request.params['page'] = info['page'] + 1

    def send(self):
        """Send request and process response."""
        if self.payload:
            self.request.headers['Content-Type'] = 'application/json'
            self.request.data = json.dumps(self.payload)
        prepared = self.session.prepare_request(self.request)
        response = self.session.send(prepared)
        try:
            data = response.json()
        except Exception:
            raise APIError(response)
        if not data.get('success', False):
            raise APIError(response)
        return data


class APIError(Exception):

    def __init__(self, response):
        self.response = response

    def __str__(self):
        template = 'CloudFlare API {} at {} failed with status code {}:\n{}'
        return template.format(
            self.response.request.method,
            self.response.request.url,
            self.response.status_code,
            self.response.text)
