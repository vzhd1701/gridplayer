# The libmpv the Windows package bundles (64-bit).
# Sourced by scripts/pyinstaller/build_win.sh and by CI's Windows tests.

# shinchiro's libmpv builds, the ones mpv.io points to for Windows. GitHub
# keeps only the last month of them, the SourceForge mirror keeps a weekly
# one for good, so it comes from there.
LIBMPV_BUILD="20261108-git-55d3feb45c"
LIBMPV_ARCHIVE="mpv-dev-x86_64-$LIBMPV_BUILD.7z"
LIBMPV_SHA256="7c147cb7ceaba717414e782ef4398de728f679db6e86daaa8aeb175670cb7994"
LIBMPV_URL="https://downloads.sourceforge.net/project/mpv-player-windows/libmpv/$LIBMPV_ARCHIVE"
# the mpv commit the build is of, which GitHub takes short
LIBMPV_COMMIT="${LIBMPV_BUILD##*-git-}"
