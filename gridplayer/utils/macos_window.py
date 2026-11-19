"""macOS: a window of our own shown over the player, going without AppKit's
animation.

Qt gives a tooltip window, as it does a popup, AppKit's utility window
animation: hidden, it fades out. Before that AppKit takes a picture of it,
and waits on the WindowServer for it, a few hundred milliseconds on the
GUI thread: every video stalls at once. The marks of a drag (a tile's
frame, the lines it snaps to, the word by the pointer) are hidden together
as it is let go of.
"""

from PyQt6.QtWidgets import QWidget

from gridplayer.params import env

# NSWindowAnimationBehaviorNone
_ANIMATION_NONE = 2


def without_window_animation(widget: QWidget) -> None:
    """Shown and hidden at once. Called each time it is shown: Qt can make
    the native window anew."""

    if not env.IS_MACOS:
        return

    import objc

    view = objc.objc_object(c_void_p=int(widget.winId()))
    window = view.window()
    if window is not None:
        window.setAnimationBehavior_(_ANIMATION_NONE)
