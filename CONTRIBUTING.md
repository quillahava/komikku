# Contributing

## Newcomers

The application is built using Python, GTK4, Libadwaita and other GNOME technologies around it. It's designed to run on either desktop or mobile.

Here are a few links to help you get started with Python, the GTK Python bindings and GNOME Builder:

- [Learn Python](https://www.learnpython.org/)
- [Python API Reference](https://amolenaar.github.io/pgi-docgen/)
- [C API Reference](https://docs.gtk.org/)
- [Tutorials](https://developer.gnome.org/documentation/tutorials.html)
- [PyGObject Guide](https://rafaelmardojai.pages.gitlab.gnome.org/pygobject-guide/)
- [GNOME Builder](https://wiki.gnome.org/Apps/Builder)

Don't hesitate to join [our Matrix room](https://matrix.to/#/#komikku-gnome:matrix.org) to come talk to us and ask us any questions you might have.

If you want to work on fixing a bug, improving something or adding a new feature, it is recommended to discuss it first in the chat room or by creating an issue.

## Build Instructions

### Building with GNOME Builder

Using [GNOME Builder](https://wiki.gnome.org/Apps/Builder) with [Flatpak](https://flatpak.org/) is
the simplest way of building and installing Komikku.

First, you will need to manually add the Flathub remote.

```sh
# Add Flathub repo
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
```

Next, install GNOME Builder:
```sh
# Install GNOME Builder
flatpak install --user flathub org.gnome.Builder
```

Then, open __GNOME Builder__, click the **Clone...** button and paste the repository url.

By default, GNOME Builder should select the `info.febvre.Komikku.json` manifest, which is the
manifest used for building the Gitlab CI pipeline version.

### Building from source

If you decide to build on your host system, outside of Flatpak, here are some general instructions.

Komikku can be built in a Python virtual environment. However, some tools and dependencies need to be installed at the system level with some of them having minimal versions:

* `meson` >= 0.59.0
* `python` >= 3.8
* `gtk` >= 4.8.1
* `libadwaita` >= 1.2.0

1. So, let's start with the system dependencies:

    Here, we take the Debian distribution (bookworm) as example.
    Sorry not to be more precise here, you will have to find the names of the corresponding packages according to the distribution you use.

    ```sh
    # Install system dependencies
    apt install make meson gettext appstream-util desktop-file-utils
    apt install python3 python3-dev python3-venv
    apt install libadwaita-1-dev libcairo2-dev libnotify-dev libmagic1 libwebkitgtk-6.0-4
    ```

2. Clone the repository:
    ```sh
    git clone https://gitlab.com/valos/Komikku.git
    cd Komikku
    ```

3. Create a virtual environment and install Python dependencies:
    ```sh
    # Create venv
    python3 -m venv .venv

    # Activate venv
    source .venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt
    pip install -r requirements-dev.txt

    # Install pre-commit hooks
    pre-commit install
    ```

    NOTE: Python package `file-magic` is an possible alternative to `python-magic`.

4. Setup build folder:
    ```sh
    make setup
    make develop
    ```

5. Run:
    ```sh
    make run
    ```
​

To test changes you make to the code, re-run the last step.

## Coding conventions

- Follow Python best practices, of course: [PEP8](https://www.python.org/dev/peps/pep-0008/)
- Indentation of 4 spaces (implies no tabs and even less a mix of both)
- Code, comments, and strings are written in English
- Variable / function / class / method / module names are clear and concise
- The code is ventilated and documented
- Use of single quotes by default, reversing if necessary, e.g. "doesn't", and triple-double quotes for multi-line: """ """
- Factoring when possible
- Clear algorithms, think of the future reader who may be yourself!
- As far as possible, avoid files that are too long (> 1000 lines)
- The order of writing a module is as follows (each block is written in alphabetical order):
    - Import native modules
    - Import modules from third party libraries
    - Import modules from the project
    - Global variables
    - Classes
    - Functions
- One import per line
- `from module import *` is FORBIDDEN
- The order of writing a class is as follows (each block is written in alphabetical order):
    - Class attributes
    - Method `__init__()`
    - Class methods
    - Properties
    - Methods `__xxx__()`
    - Methods `__xxx()`
    - Methods and static methods (which should not be used)
- Number string formatting arguments: '{0} - {1}'.format('one', 'two')
- Variables are suffixed with _ when they have a built-ins name (e.g. type_)

## Commit

We expect all code contributions to be checked with `pycodestyle` and `flake8`.

### Commit Message Example

```
[Tag] Short explanation of the commit

Longer explanation explaining exactly what's changed and why,
what issue were fixed (with issue number if applicable) and so forth.
Be concise but not too brief.

Fixes #123456
```

### Commit Message Details

- The commit message is mainly for the other people, so they should be able to understand it now and six months later.
- Always add a brief description of the commit to the first line of the commit and terminate by two newlines (it will work without the second newline, but that is not nice for the interfaces).
- First line (the brief description) must only be one sentence and should start with a capital letter unless it starts with a lowercase symbol or identifier. Don't use a trailing period either. It's recommended to not exceed 50 characters but it's not always possible/easy to follow this limit. In any case, don't exceed 72 characters.
- You can prefix the first line with one tag, to make it easier to know to which part the commit applies. For example, a commit with "[Library] Improve thumbnails rendering" clearly applies to the library page.
- The description part (the body) is normal prose and should use normal punctuation and capital letters where appropriate.  This description part can be empty if the change is self-explanatory.
- Each line in description must not exceed 75 characters (there is no limit on number of lines).
- When committing code on behalf of others use the --author option, e.g. git commit -a --author "Joe Coder <joe@coder.org>".
- Use imperative form of verbs rather than past tense when referring to changes introduced by commit in question. For example "Remove property X" rather than "Removed property X".

## Merge Request

Before submitting a merge request, make sure that [your fork is available publicly](https://gitlab.gnome.org/help/user/public_access.md), otherwise CI won't be able to run.

Use the title of your commit as the title of your MR if there's only one. Otherwise it should summarize all your commits. If your commits do several tasks that can be separated, open several merge requests.

In the details, write a more detailed description of what it does. If your changes include a change in the UI or the UX, provide screenshots in both light and dark mode, and/or a screencast of the new behavior.

Don't forget to mention the issue that this merge request solves or is related to, if applicable. GitLab recognizes the syntax `Closes #XXXX` or `Fixes #XXXX` that will close the corresponding issue accordingly when your change is merged.

We expect to always work with a clean commit history. When you apply fixes or suggestions,
[amend](https://git-scm.com/docs/git-commit#Documentation/git-commit.txt---amend) or
[fixup](https://git-scm.com/docs/git-commit#Documentation/git-commit.txt---fixupamendrewordltcommitgt)
and [squash](https://git-scm.com/docs/git-rebase#Documentation/git-rebase.txt---autosquash) your
previous commits that you can then [force push](https://git-scm.com/docs/git-push#Documentation/git-push.txt--f).
