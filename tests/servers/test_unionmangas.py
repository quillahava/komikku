import logging
import pytest
from pytest_steps import test_steps

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def unionmangas_server():
    from komikku.servers.unionmangas import Unionmangas

    return Unionmangas()


@test_steps('get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_unionmangas(unionmangas_server):
    # Get most populars
    print('Get most populars')
    try:
        response = unionmangas_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        # Use first result of get_most_populars
        response = unionmangas_server.search(response[0]['name'])
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = unionmangas_server.get_manga_data(dict(slug=slug))
        name = response['name']
        chapter_slug = response['chapters'][0]['slug']
        chapter_url = response['chapters'][0]['url']
    except Exception as e:
        chapter_slug = None
        chapter_url = None
        log_error_traceback(e)

    assert chapter_slug is not None
    assert chapter_url is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = unionmangas_server.get_manga_chapter_data(None, None, None, chapter_url)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = unionmangas_server.get_manga_chapter_page_image(None, name, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
