import logging
import pytest
from pytest_steps import test_steps

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def fmteam_server():
    from komikku.servers.fmteam import Fmteam

    return Fmteam()


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_fmteam(fmteam_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = fmteam_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most popular
    print('Get most popular')
    try:
        response = fmteam_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        # Use first result of get_most_populars
        response = fmteam_server.search(response[0]['name'])
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = fmteam_server.get_manga_data(dict(slug=slug))
        chapter_url = response['chapters'][0]['url']
    except Exception as e:
        chapter_url = None
        log_error_traceback(e)

    assert chapter_url is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = fmteam_server.get_manga_chapter_data(slug, None, None, chapter_url)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = fmteam_server.get_manga_chapter_page_image(None, None, None, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
