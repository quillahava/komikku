import logging
import pytest
from pytest_steps import test_steps

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def peppercarrot_server():
    from komikku.servers.peppercarrot import Peppercarrot

    return Peppercarrot()


@test_steps('get_manga_data', 'get_chapter_data', 'get_page_image')
def test_peppercarrot(peppercarrot_server):
    # Get most populars
    print('Get most populars')
    try:
        response = peppercarrot_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = peppercarrot_server.get_manga_data(response[0])
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = peppercarrot_server.get_manga_chapter_data(None, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = peppercarrot_server.get_manga_chapter_page_image(None, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
