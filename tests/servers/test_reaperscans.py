import logging
import pytest
from pytest_steps import test_steps

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def reaperscans_server():
    from komikku.servers.reaperscans import Reaperscans

    return Reaperscans()


@pytest.fixture
def reaperscans_fr_server():
    from komikku.servers.reaperscans import Reaperscans_fr

    return Reaperscans_fr()


@pytest.fixture
def reaperscans_pt_server():
    from komikku.servers.reaperscans import Reaperscans_pt

    return Reaperscans_pt()


@test_steps('get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans(reaperscans_server):
    # Get most populars
    print('Get most populars')
    try:
        response = reaperscans_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        response = reaperscans_server.search('leveling with the gods')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = reaperscans_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = reaperscans_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = reaperscans_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans_fr(reaperscans_fr_server):
    # Get most populars
    print('Get most populars')
    try:
        response = reaperscans_fr_server.get_most_populars('all')
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        response = reaperscans_fr_server.search('sss', 'all')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = reaperscans_fr_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = reaperscans_fr_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = reaperscans_fr_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans_pt(reaperscans_pt_server):
    # Get most populars
    print('Get most populars')
    try:
        response = reaperscans_pt_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        response = reaperscans_pt_server.search('return of the legendary spear knight')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = reaperscans_pt_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = reaperscans_pt_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = reaperscans_pt_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
