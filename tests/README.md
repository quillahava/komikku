## Test inside a virtual environment

1. Create venv

    ```bash
    python3 -m venv .venv
    ```

2. Activate venv

    ```bash
    source .venv/bin/activate
    ```

3. Install dependencies + pytest

    ```bash
    pip install --upgrade pip setuptools wheel
    pip install PyGObject
    pip install natsort
    pip install pillow
    pip install beautifulsoup4
    pip install lxml
    pip install cloudscraper
    pip install dateparser
    pip install python-magic
    pip install keyring
    pip install unidecode
    pip install pure-protobuf

    pip install pytest
    pip install pytest-steps
    ```

## Run tests

    ```bash
    python -m pytest -v
    ```
