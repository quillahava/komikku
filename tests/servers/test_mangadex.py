import logging
import pytest
from pytest_steps import test_steps, optional_step

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def mangadex_server():
    from komikku.servers.mangadex import Mangadex

    return Mangadex()


@test_steps('get_latest_updates', 'get_most_popular', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_mangadex(mangadex_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = mangadex_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most popular
    print('Get most popular')
    with optional_step('get_most_popular') as step:
        try:
            response = mangadex_server.get_most_populars()
        except Exception as e:
            response = None
            log_error_traceback(e)

        assert response is not None
    yield step

    # Search
    print('Search')
    try:
        response = mangadex_server.search('tales of demons and gods')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = mangadex_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = mangadex_server.get_manga_chapter_data(None, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = mangadex_server.get_manga_chapter_page_image(None, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
