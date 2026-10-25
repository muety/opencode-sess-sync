import httpx2


class SyncError(Exception):
    pass


class OpenCodeClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        auth = httpx2.BasicAuth('opencode', token) if token else None
        self._http = httpx2.Client(base_url=base_url, auth=auth, timeout=60)

    def info(self) -> dict:
        return self._get('/api/info').json()

    def list_sessions(self) -> dict[str, dict]:
        sessions: dict[str, dict] = {}
        cursor = None
        while True:
            params = {'order': 'desc', 'limit': '500'} if cursor is None else {'cursor': cursor}
            body = self._get('/api/session', params=params).json()
            sessions.update({item['id']: item for item in body['data']})
            cursor = (body.get('cursor') or {}).get('next')
            if not cursor:
                return sessions

    def active_session_ids(self) -> set[str]:
        return set(self._get('/api/session/active').json()['data'])

    def export_session(self, session_id: str) -> dict:
        return self._get(f'/api/experimental/session/{session_id}/export').json()['data']

    def import_session(self, snapshot: dict, directory: str | None = None) -> dict:
        body: dict = {'info': snapshot['info'], 'messages': snapshot['messages']}
        if directory:
            body['location'] = {'directory': directory}
        return self._request('POST', '/api/experimental/session/import', json=body).json()['data']

    def delete_session(self, session_id: str) -> None:
        response = self._http.delete(f'/api/session/{session_id}')
        if response.status_code != 404:
            self._check(response)

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict | None = None) -> httpx2.Response:
        return self._request('GET', path, params=params)

    def _request(self, method: str, path: str, params: dict | None = None, json: dict | None = None) -> httpx2.Response:
        response = self._http.request(method, path, params=params, json=json)
        self._check(response)
        return response

    @staticmethod
    def _check(response: httpx2.Response) -> None:
        if response.status_code >= 400:
            raise SyncError(f'{response.request.method} {response.url} -> {response.status_code}: {response.text[:200]}')
