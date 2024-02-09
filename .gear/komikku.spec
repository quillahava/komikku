%define gtk4_version 4.12.5
%define libadwaita_version 1.4.2
%define _metainfodir %{_datadir}/metainfo

Name:           komikku
Version:        1.37.1
Release:        alt1
Summary:        A manga reader for GNOME
Group:          Books/Other
BuildArch:      noarch

License:        GPL-3.0-or-later
URL:            https://valos.gitlab.io/Komikku
Source0:        %{name}-%{version}.tar

BuildRequires(pre): rpm-macros-meson
BuildRequires:  cmake
BuildRequires:  glib2-devel
BuildRequires:  gobject-introspection-devel
BuildRequires:  libgtk4-devel
BuildRequires:  libadwaita-devel
BuildRequires:  libadwaita
BuildRequires:  libadwaita-gir
BuildRequires:  desktop-file-utils
BuildRequires:  intltool
BuildRequires:  libappstream-glib
BuildRequires:  meson
BuildRequires:  python3-dev
BuildRequires:  blueprint-compiler
BuildRequires: python3-module-pkgconfig

Requires:       icon-theme-hicolor
Requires:       libgtk4
Requires:       libadwaita
Requires:       libnotify
Requires:       libwebkitgtk6.0
Requires:       python3-module-beautifulsoup4
Requires:       python3-module-brotli
Requires:       python3-module-colorthief
Requires:       python3-module-dateparser
Requires:       python3-module-emoji
Requires:       python3-module-pygobject
Requires:       python3-module-keyring
Requires:       python3-module-lxml
Requires:       python3-module-natsort
# The conflict between python-magic and python-file-magic should be brought to
# FESCO.
Requires:       python3-module-magic
Requires:       python3-module-piexif
Requires:       python3-module-Pillow
Requires:       python3-module-pure-protobuf == 2.3.0
Requires:       python3-module-rarfile
Requires:       python3-module-requests
Requires:       python3-module-unidecode

%description
Komikku is a manga reader for GNOME. It focuses on providing a clean, intuitive
and adaptive interface.

Keys features

* Online reading from dozens of servers
* Offline reading of downloaded comics
* Categories to organize your library
* RTL, LTR, Vertical and Webtoon reading modes
* Several types of navigation:
  * Keyboard arrow keys
  * Right and left navigation layout via mouse click or tapping
    (touchpad/touch screen)
  * Mouse wheel
  * 2-fingers swipe gesture (touchpad)
  * Swipe gesture (touch screen)
* Automatic update of comics
* Automatic download of new chapters
* Reading history
* Light and dark themes

%prep
#autosetup -n %{name} -p1
%setup -v
export GI_TYPELIB_PATH=/usr/lib64/girepository-1.0



%build
%meson
%meson_build


%install
%meson_install
%find_lang %{name}
install -Dm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE


%check
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/*.xml
desktop-file-validate %{buildroot}%{_datadir}/applications/*.desktop


%post
glib-compile-schemas %{_datadir}/glib-2.0/schemas/


%postun
glib-compile-schemas %{_datadir}/glib-2.0/schemas/


%files -f %{name}.lang
%doc README.md CODE_OF_CONDUCT.md
%{_bindir}/%{name}
%{_datadir}/%{name}/
%{_datadir}/applications/*.desktop
%{_datadir}/glib-2.0/schemas/*.gschema.xml
%{_datadir}/icons/hicolor/scalable/*/*.svg
%{_datadir}/icons/hicolor/symbolic/*/*.svg
%{_metainfodir}/*.xml
%{python3_sitelibdir}/%{name}/
%_licensedir/%name/LICENSE


%changelog
* Fri Feb 9 2024 Aleksandr A. Voyt <vojtaa@basealt.ru> 1.37.1-alt1
- First package version
