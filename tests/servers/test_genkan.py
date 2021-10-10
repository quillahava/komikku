import logging
import pytest
from pytest_steps import test_steps

from komikku.utils import log_error_traceback

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def edelgardescans_server():
    from komikku.servers.edelgardescans import Edelgardescans

    return Edelgardescans()


@pytest.fixture
def hatigarmscans_server():
    from komikku.servers.hatigarmscans import Hatigarmscans

    return Hatigarmscans()


@pytest.fixture
def hunlightscans_server():
    from komikku.servers.hunlightscans import Hunlightscans

    return Hunlightscans()


@pytest.fixture
def thenonamesscans_server():
    from komikku.servers.thenonamesscans import Thenonamesscans

    return Thenonamesscans()


@pytest.fixture
def zeroscans_server():
    from komikku.servers.zeroscans import Zeroscans

    return Zeroscans()


@test_steps('get_most_popular', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_edelgardescans(edelgardescans_server):
    # Get most popular
    print('Get most popular')
    try:
        response = edelgardescans_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        response = edelgardescans_server.search('the gateway of revolution')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = edelgardescans_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = edelgardescans_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = edelgardescans_server.get_manga_chapter_page_image(None, None, None, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_most_popular', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_hatigarmscans(hatigarmscans_server):
    # Get most popular
    print('Get most popular')
    try:
        response = hatigarmscans_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        response = hatigarmscans_server.search('tales of demons and gods')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = hatigarmscans_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = hatigarmscans_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = hatigarmscans_server.get_manga_chapter_page_image(None, None, None, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_most_popular', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_hunlightscans(hunlightscans_server):
    # Get most popular
    print('Get most popular')
    try:
        response = hunlightscans_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        response = hunlightscans_server.search('ossan boukensha kane no zenkou')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = hunlightscans_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = hunlightscans_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = hunlightscans_server.get_manga_chapter_page_image(None, None, None, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_most_popular', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_thenonamesscans(thenonamesscans_server):
    # Get most popular
    print('Get most popular')
    try:
        response = thenonamesscans_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        response = thenonamesscans_server.search('player reborn')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = thenonamesscans_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = thenonamesscans_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = thenonamesscans_server.get_manga_chapter_page_image(None, None, None, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield


@test_steps('get_most_popular', 'search', 'get_manga_data', 'get_chapter_data', 'get_page_image')
def test_zeroscans(zeroscans_server):
    # Get most popular
    print('Get most popular')
    try:
        response = zeroscans_server.get_most_populars()
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield

    # Search
    print('Search')
    try:
        response = zeroscans_server.search('second life ranker')
        slug = response[0]['slug']
    except Exception as e:
        slug = None
        log_error_traceback(e)

    assert slug is not None
    yield

    # Get manga data
    print('Get manga data')
    try:
        response = zeroscans_server.get_manga_data(dict(slug=slug))
        chapter_slug = response['chapters'][0]['slug']
    except Exception as e:
        chapter_slug = None
        log_error_traceback(e)

    assert chapter_slug is not None
    yield

    # Get chapter data
    print("Get chapter data")
    try:
        response = zeroscans_server.get_manga_chapter_data(slug, None, chapter_slug, None)
        page = response['pages'][0]
    except Exception as e:
        page = None
        log_error_traceback(e)

    assert page is not None
    yield

    # Get page image
    print('Get page image')
    try:
        response = zeroscans_server.get_manga_chapter_page_image(None, None, None, page)
    except Exception as e:
        response = None
        log_error_traceback(e)

    assert response is not None
    yield
