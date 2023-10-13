message('Install icons')

# Scalable
scalable_dir = join_paths(datadir, 'icons/hicolor/scalable/apps')
profile = get_option('profile')
if profile == 'beta'
    install_data (
        '@0@.Devel.svg'.format(base_id),
        install_dir: scalable_dir,
        rename: '@0@.svg'.format(app_id)
    )
else
    install_data (
        '@0@.svg'.format(app_id),
        install_dir: scalable_dir,
    )
endif

# Symbolic
symbolic_dir = join_paths(datadir, 'icons/hicolor/symbolic/apps')
install_data (
    '@0@-symbolic.svg'.format(base_id),
    install_dir: symbolic_dir,
    rename: '@0@-symbolic.svg'.format(app_id)
)

install_data (
    'brush-symbolic.svg',
    install_dir: symbolic_dir
)
install_data (
    'computer-fail-symbolic.svg',
    install_dir: symbolic_dir
)
install_data (
    'explore-symbolic.svg',
    install_dir: symbolic_dir
)
install_data (
    'grid-symbolic.svg',
    install_dir: symbolic_dir
)
