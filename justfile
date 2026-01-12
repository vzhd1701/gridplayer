default:
    just --list

build-requirements:
    if [ ! -f build/requirements.txt ]; then mkdir -p build && poetry export --without-hashes -o build/requirements.txt; fi

build:
    poetry build

build-wheel:
    if [ ! -f dist/*.whl ]; then poetry build -f wheel; fi

build-sdist:
    if [ ! -f dist/*.tar.gz ]; then poetry build -f sdist; fi

build-linux-meta:
    ./scripts/linux_meta/build.sh

build-linux-appimage: build-wheel build-linux-meta
    ./scripts/appimage/build.sh

build-linux-snap: build-wheel build-linux-meta
    ./scripts/snap/build.sh

build-linux-snap-no-build: build-wheel build-linux-meta
    ./scripts/snap/build.sh --no-build

build-linux-flatpak: build-requirements build-sdist build-linux-meta
    ./scripts/flatpak/build.sh

build-linux-flatpak-git: build-requirements build-sdist build-linux-meta
    ./scripts/flatpak/build_git.sh

build-win-pyinstaller: build-requirements
    ./scripts/pyinstaller/build_win.sh

build-win-package: build-win-pyinstaller
    ./scripts/windows/build_packages.sh

build-macos-pyinstaller: build-requirements
    ./scripts/pyinstaller/build_mac.sh

build-macos-package: build-macos-pyinstaller
    ./scripts/macos/build_dmg.sh

clean-pyinstaller-dist:
    find dist -maxdepth 1 -mindepth 1 -type d -exec rm -r {} \;

generate-ui:
    ./scripts/qt_resources/build_ui.sh

generate-resources:
    ./scripts/qt_resources/build_resources.sh

changelog:
    conventional-changelog -p conventionalcommits -u -a --stdout | sed -n '0,/\[0\.1\.0\]:/d; p'

changelog-all:
    conventional-changelog -u -a --stdout | sed -n '0,/\[0\.1\.0\]:/d; p'
