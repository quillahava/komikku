glade_conf = configuration_data()

glade_conf.set('app_id', app_id)
glade_conf.set('website', website)
glade_conf.set('DATA_DIR', pkgdatadir)
glade_conf.set('gitrepo', gitrepo)

# This is for development version
#glade_conf.set('version', ''.join([run_command(['git', 'describe', '--long', '--tags']).stdout(), get_option('profile')]))
glade_conf.set('version', meson.project_version())

glade_conf.set('authorfullname', authorfullname)
if profile == 'beta'
    glade_conf.set('prettyname', prettyname + ' (beta)')
elif profile == 'development'
    glade_conf.set('prettyname', prettyname + ' (devel)')
else
    glade_conf.set('prettyname', prettyname)
endif
