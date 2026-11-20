# The VLC the Windows package bundles, for BUILD_WIN_ARCH (x64, the
# default, or arm64).
# Sourced by scripts/pyinstaller/build_win.sh and by CI's Windows arm64
# tests, for which Chocolatey has only the x64 VLC.

# VideoLAN's own server: get.videolan.org can pick a mirror running at a
# few KB/s. The SHA-256s are the ones published beside each file.
VLC_VERSION="3.0.24"

case "${BUILD_WIN_ARCH:-x64}" in
    x64)
        VLC_ARCH="win64"
        VLC_SHA256="fcf30850371ad10c9373cc4f0f4501e7dee49e3e9ae9f20c72fb2661a1ca6323"
        ;;
    arm64)
        VLC_ARCH="winarm64"
        VLC_SHA256="f096226211f67f8e06e50cd0d6a948d842db128ff22a676dc1ca1cc6114baba5"
        ;;
    *)
        echo "Unsupported Windows architecture: $BUILD_WIN_ARCH" >&2
        exit 1
        ;;
esac

VLC_ARCHIVE="vlc-$VLC_VERSION-$VLC_ARCH.zip"
VLC_URL="https://download.videolan.org/pub/videolan/vlc/$VLC_VERSION/$VLC_ARCH/$VLC_ARCHIVE"
