# The libmpv the Windows package bundles, for BUILD_WIN_ARCH (x64, the
# default, or arm64).
# Sourced by scripts/pyinstaller/build_win.sh and by CI's Windows tests.

# shinchiro's libmpv builds, the ones mpv.io points to for Windows. GitHub
# keeps only the last month of them, the SourceForge mirror keeps a weekly
# one for good, so it comes from there. SourceForge publishes no hashes:
# these are of the files as downloaded.
LIBMPV_BUILD="20261108-git-55d3feb45c"

case "${BUILD_WIN_ARCH:-x64}" in
    x64)
        LIBMPV_ARCHIVE="mpv-dev-x86_64-$LIBMPV_BUILD.7z"
        LIBMPV_SHA256="7c147cb7ceaba717414e782ef4398de728f679db6e86daaa8aeb175670cb7994"
        ;;
    arm64)
        LIBMPV_ARCHIVE="mpv-dev-aarch64-$LIBMPV_BUILD.7z"
        LIBMPV_SHA256="f7d3b2d97d07b5758cb277412ed95dc55aac2112397b6d06161d0b58c3e941fc"
        ;;
    *)
        echo "Unsupported Windows architecture: $BUILD_WIN_ARCH" >&2
        exit 1
        ;;
esac

LIBMPV_URL="https://downloads.sourceforge.net/project/mpv-player-windows/libmpv/$LIBMPV_ARCHIVE"
# the mpv commit the build is of, which GitHub takes short
LIBMPV_COMMIT="${LIBMPV_BUILD##*-git-}"
