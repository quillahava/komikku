project('komikku',
    version: '1.6.0',
    meson_version: '>= 0.59.0',
    license: 'GPL-3.0-or-later'
)

description = 'A manga reader for GNOME'
prettyname = 'Komikku'

authornickname = 'valos'
authorfullname = 'Valéry Febvre'
authoremail = 'vfebvre@easter-eggs.com'

# app_id built as: domainext.domainname.prettyname
domainname = 'febvre'
domainext = 'info'

gitrepo = 'https://gitlab.com/' + authornickname + '/' + prettyname
website = 'https://valos.gitlab.io/Komikku/'

python = import('python')
py_installation = python.find_installation('python3')
if not py_installation.found()
    error('No valid python3 binary found')
else
    message('Found python3 binary')
endif

prefix = get_option('prefix') # should be /usr
profile = get_option('profile') # should be default, development or beta
bindir = get_option('bindir') # should be /bin
datadir = get_option('datadir') # should be /usr/share
pkgdatadir = join_paths(prefix, datadir, meson.project_name())
pythondir = py_installation.get_install_dir()
localedir = join_paths(prefix, get_option('localedir'))

base_id = '.'.join([domainext, domainname, prettyname])
app_id_aspath = '/'.join([domainext, domainname, prettyname])
if profile == 'development'
    app_id = base_id + '.Devel'
else
    app_id = base_id
endif

install_subdir(meson.project_name(), install_dir: pythondir)

subdir('data')
subdir('bin')
subdir('po')

# Run required post-install steps
gnome.post_install(
    gtk_update_icon_cache: true,
    glib_compile_schemas: true,
    update_desktop_database: true,
)
