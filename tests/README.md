## Test inside a virtual environment

1. Create venv (in root folder)

    ```sh
    python3 -m venv .venv
    ```

2. Activate venv

    ```sh
    source .venv/bin/activate
    ```

3. Install dependencies

    ```sh
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
    ```

4. Install

    ```sh
    make setup
    make develop
    ```


## Run tests

```sh
make test
```

OR to test a single server:

```sh
make test TEST_PATH=./tests/servers/test_xkcd.py
```
