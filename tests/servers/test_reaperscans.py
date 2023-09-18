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
def reaperscans_ar_server():
    from komikku.servers.reaperscans import Reaperscans_ar

    return Reaperscans_ar()


@pytest.fixture
def reaperscans_id_server():
    from komikku.servers.reaperscans import Reaperscans_id

    return Reaperscans_id()


@pytest.fixture
def reaperscans_pt_br_server():
    from komikku.servers.reaperscans import Reaperscans_pt_br

    return Reaperscans_pt_br()


@pytest.fixture
def reaperscans_tr_server():
    from komikku.servers.reaperscans import Reaperscans_tr

    return Reaperscans_tr()


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans(reaperscans_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = reaperscans_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

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
        response = reaperscans_server.search(response[0]['name'])
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


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans_ar(reaperscans_ar_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = reaperscans_ar_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most populars
    print('Get most populars')
    try:
        response = reaperscans_ar_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        response = reaperscans_ar_server.search(response[0]['name'])
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = reaperscans_ar_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = reaperscans_ar_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = reaperscans_ar_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans_id(reaperscans_id_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = reaperscans_id_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most populars
    print('Get most populars')
    try:
        response = reaperscans_id_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        response = reaperscans_id_server.search(response[0]['name'])
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = reaperscans_id_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = reaperscans_id_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = reaperscans_id_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans_pt_br(reaperscans_pt_br_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = reaperscans_pt_br_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most populars
    print('Get most populars')
    try:
        response = reaperscans_pt_br_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        response = reaperscans_pt_br_server.search(response[0]['name'])
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = reaperscans_pt_br_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = reaperscans_pt_br_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = reaperscans_pt_br_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_latest_updates', 'get_most_populars', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_reaperscans_tr(reaperscans_tr_server):
    # Get latest updates
    print('Get latest updates')
    try:
        response = reaperscans_tr_server.get_latest_updates()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Get most populars
    print('Get most populars')
    try:
        response = reaperscans_tr_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response
    yield

    # Search
    print('Search')
    try:
        response = reaperscans_tr_server.search(response[0]['name'])
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = reaperscans_tr_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = reaperscans_tr_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = reaperscans_tr_server.get_manga_chapter_page_image(slug, None, chapter_slug, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
