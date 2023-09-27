# Profiles
conf = configuration_data()

conf.set_quoted('PROFILE', profile)
conf.set('VERSION', meson.project_version())
conf.set('PYTHON', py_installation.full_path())
conf.set('prefix', prefix)
conf.set('datadir', datadir)
conf.set('pkgdatadir', pkgdatadir)
conf.set('pythondir', join_paths(prefix, pythondir))
conf.set('localedir', join_paths(prefix, localedir))
conf.set('projectname', meson.project_name())
conf.set('prettyname', prettyname)
conf.set('description', description)
conf.set('authorfullname', authorfullname)
conf.set('authoremail', authoremail)
conf.set('appid', app_id)

# Install launch script and add `run` target
configure_file(
  input: meson.project_name() + '.in',
  output: meson.project_name(),
  configuration: conf,
  install: true,
  install_dir: get_option('bindir')
)

script_path = join_paths(meson.project_build_root(), 'bin', meson.project_name())
run_target('run',
  command: [script_path]
)

# Install tests script and add `tests` target
if profile == 'development'
    configure_file(
      input: meson.project_name() + '-tests.in',
      output: meson.project_name() + '-tests',
      configuration: conf,
      install: true,
      install_dir: get_option('bindir')
    )

    tests_script_path = join_paths(meson.project_build_root(), 'bin', meson.project_name() + '-tests')
    run_target('tests',
      command: [tests_script_path]
    )
endif
