import logging
import pytest
from pytest_steps import test_steps

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def coloredcouncil_server():
    from komikku.servers.coloredcouncil import Coloredcouncil

    return Coloredcouncil()


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_coloredcouncil(coloredcouncil_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = coloredcouncil_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most populars (empty search)
    print('Get most populars')
    try:
        response = coloredcouncil_server.search('')
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        # Use second result of get_most_populars
        term = response[1]['name'].split('–')[0]
        response = coloredcouncil_server.search(term)
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = coloredcouncil_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = coloredcouncil_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = coloredcouncil_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
