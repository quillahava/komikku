import logging
import pytest
from pytest_steps import test_steps

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def readcomiconline_server():
    from komikku.servers.readcomiconline import Readcomiconline

    return Readcomiconline()


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data')
def test_readcomiconline(readcomiconline_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = readcomiconline_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most popular
    print('Get most popular')
    try:
        response = readcomiconline_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        # Use first result of get_most_populars
        response = readcomiconline_server.search(response[0]['name'])
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = readcomiconline_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    assert len(response['chapters']) > 0
    yield
