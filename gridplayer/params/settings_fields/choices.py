"""What a choice offers, value -> text.

Functions rather than dicts so the texts are translated when a form is
built, not when this is imported.
"""

import logging

from PyQt5.QtGui import QFontDatabase

from gridplayer.params import env
from gridplayer.params.static import (
    AddMode,
    AudioChannelMode,
    AudioTrackMode,
    CacheMode,
    ColorScheme,
    DropAction,
    GridMode,
    HWCropBorderOffset,
    ListEndAction,
    ListFailAction,
    ListUpdate,
    ListView,
    NetworkRetryMode,
    ProxyMode,
    ScreenshotFormat,
    SeekSyncMode,
    SponsorBlockMode,
    SubtitleOutline,
    SubtitleTrackMode,
    UnsavedChangesMode,
    URLResolver,
    VideoAnchor,
    VideoAspect,
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoDriver,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.params.subtitle_encodings import SUBTITLE_ENCODINGS
from gridplayer.utils import log_config
from gridplayer.utils.qt import translate


def grid_modes() -> dict:
    return {
        GridMode.AUTO_ROWS: translate("Grid Mode", "Auto (Rows First)"),
        GridMode.AUTO_COLS: translate("Grid Mode", "Auto (Columns First)"),
        GridMode.FIXED: translate("Grid Mode", "Fixed Grid"),
    }


def seek_sync_modes() -> dict:
    return {
        SeekSyncMode.DISABLED: translate("Seek Sync", "Disabled"),
        SeekSyncMode.PERCENT: translate("Seek Sync", "Percent"),
        SeekSyncMode.TIMECODE: translate("Seek Sync", "Timecode"),
    }


def unsaved_changes_modes() -> dict:
    return {
        UnsavedChangesMode.ASK: translate("SettingsDialog", "Ask"),
        UnsavedChangesMode.DISCARD: translate("SettingsDialog", "Discard Changes"),
        UnsavedChangesMode.AUTO_SAVE_DISCARD: translate(
            "SettingsDialog", "Auto Save or Discard"
        ),
        UnsavedChangesMode.AUTO_SAVE_ASK: translate(
            "SettingsDialog", "Auto Save or Ask"
        ),
    }


def drop_internal() -> dict:
    return {
        DropAction.INSERT: translate("SettingsDialog", "Move / Swap"),
        DropAction.REPLACE: translate("SettingsDialog", "Replace"),
    }


def drop_external() -> dict:
    return {
        DropAction.INSERT: translate("SettingsDialog", "Add"),
        DropAction.REPLACE: translate("SettingsDialog", "Replace"),
    }


def add_modes() -> dict:
    return {
        AddMode.CELL_EACH: translate("Adding", "One per item"),
        AddMode.ONE_CELL: translate("Adding", "One for all"),
        AddMode.CELL_PER_FILE: translate("Adding", "One per video"),
        AddMode.ASK: translate("Adding", "Ask"),
    }


def list_views() -> dict:
    return {
        ListView.TITLES: translate("SettingsDialog", "Titles"),
        ListView.TITLES_AND_LOCATIONS: translate("SettingsDialog", "Titles and paths"),
        ListView.LOCATIONS: translate("SettingsDialog", "Paths"),
    }


def list_update_txts() -> dict:
    """How often linked lists are read again, as the playlist's setting
    and each list's own choice in its List window say it."""

    return {
        ListUpdate.ON_LOAD: translate("Lists", "On playlist load"),
        ListUpdate.FIVE_MINUTES: translate("Lists", "Every 5 minutes"),
        ListUpdate.FIFTEEN_MINUTES: translate("Lists", "Every 15 minutes"),
        ListUpdate.HOURLY: translate("Lists", "Every hour"),
        ListUpdate.SIX_HOURS: translate("Lists", "Every 6 hours"),
        ListUpdate.DAILY: translate("Lists", "Every day"),
        ListUpdate.MANUAL: translate("Lists", "Manually"),
    }


def aspects() -> dict:
    return {
        VideoAspect.FIT: translate("Aspect", "Fit"),
        VideoAspect.STRETCH: translate("Aspect", "Stretch"),
        VideoAspect.NONE: translate("Aspect", "None"),
    }


def anchors() -> dict:
    return {
        VideoAnchor.CENTER: translate("Alignment", "Center"),
        VideoAnchor.TOP: translate("Alignment", "Top"),
        VideoAnchor.BOTTOM: translate("Alignment", "Bottom"),
        VideoAnchor.LEFT: translate("Alignment", "Left"),
        VideoAnchor.RIGHT: translate("Alignment", "Right"),
        VideoAnchor.TOP_LEFT: translate("Alignment", "Top Left"),
        VideoAnchor.TOP_RIGHT: translate("Alignment", "Top Right"),
        VideoAnchor.BOTTOM_LEFT: translate("Alignment", "Bottom Left"),
        VideoAnchor.BOTTOM_RIGHT: translate("Alignment", "Bottom Right"),
    }


def transforms() -> dict:
    return {
        VideoTransform.ROTATE_90: translate("Transform", "Rotate 90"),
        VideoTransform.ROTATE_180: translate("Transform", "Rotate 180"),
        VideoTransform.ROTATE_270: translate("Transform", "Rotate 270"),
        VideoTransform.HFLIP: translate("Transform", "Flip Horizontally"),
        VideoTransform.VFLIP: translate("Transform", "Flip Vertically"),
        VideoTransform.TRANSPOSE: translate("Transform", "Transpose"),
        VideoTransform.ANTITRANSPOSE: translate("Transform", "Anti-transpose"),
        VideoTransform.NONE: translate("Transform", "No Transform"),
    }


def deinterlace_states() -> dict:
    # in the menu's own contexts, so each string is translated once for both
    return {
        VideoDeinterlace.AUTO: translate("Deinterlace", "Automatic"),
        VideoDeinterlace.ON: translate("Deinterlace", "On"),
        VideoDeinterlace.OFF: translate("Deinterlace", "Off"),
    }


def deinterlace_modes() -> dict:
    return {
        VideoDeinterlaceMode.AUTO: translate("Deinterlace Mode", "Auto"),
        VideoDeinterlaceMode.DISCARD: translate("Deinterlace Mode", "Discard"),
        VideoDeinterlaceMode.BLEND: translate("Deinterlace Mode", "Blend"),
        VideoDeinterlaceMode.MEAN: translate("Deinterlace Mode", "Mean"),
        VideoDeinterlaceMode.BOB: translate("Deinterlace Mode", "Bob"),
        VideoDeinterlaceMode.LINEAR: translate("Deinterlace Mode", "Linear"),
        VideoDeinterlaceMode.X: translate("Deinterlace Mode", "X"),
        VideoDeinterlaceMode.YADIF: translate("Deinterlace Mode", "Yadif"),
        VideoDeinterlaceMode.YADIF2X: translate("Deinterlace Mode", "Yadif (2x)"),
        VideoDeinterlaceMode.PHOSPHOR: translate("Deinterlace Mode", "Phosphor"),
        VideoDeinterlaceMode.IVTC: translate("Deinterlace Mode", "Film NTSC (IVTC)"),
    }


def end_actions() -> dict:
    return {
        VideoEndAction.LOOP_FILE: translate("When Finished", "Loop this file"),
        VideoEndAction.NEXT_FILE: translate("When Finished", "Play next file"),
        VideoEndAction.PREVIOUS_FILE: translate("When Finished", "Play previous file"),
        VideoEndAction.SHUFFLE_FILE: translate("When Finished", "Play random file"),
        VideoEndAction.PAUSE: translate("When Finished", "Pause at start"),
        VideoEndAction.STOP: translate("When Finished", "Stop"),
        VideoEndAction.CLOSE: translate("When Finished", "Close"),
    }


def list_end_actions() -> dict:
    return {
        ListEndAction.START_OVER: translate("Lists", "Start over"),
        ListEndAction.PAUSE: translate("Lists", "Pause at start"),
        ListEndAction.STOP: translate("Lists", "Stop"),
        ListEndAction.CLOSE: translate("Lists", "Close"),
    }


def list_fail_actions() -> dict:
    return {
        ListFailAction.SHOW_ERROR: translate("When Video Fails", "Show error"),
        ListFailAction.PLAY_NEXT: translate("When Video Fails", "Play next"),
    }


def initial_states() -> dict:
    return {
        VideoInitialState.PLAYING: translate("SettingsDialog", "Playing"),
        VideoInitialState.PAUSED: translate("SettingsDialog", "Paused"),
        VideoInitialState.STOPPED: translate("SettingsDialog", "Stopped"),
    }


def audio_modes() -> dict:
    return {
        AudioChannelMode.UNSET: translate("Audio Mode", "Original"),
        AudioChannelMode.STEREO: translate("Audio Mode", "Stereo"),
        AudioChannelMode.RSTEREO: translate("Audio Mode", "Reverse Stereo"),
        AudioChannelMode.LEFT: translate("Audio Mode", "Left"),
        AudioChannelMode.RIGHT: translate("Audio Mode", "Right"),
        AudioChannelMode.DOLBYS: translate("Audio Mode", "Dolby Surround"),
        AudioChannelMode.HEADPHONES: translate("Audio Mode", "Headphones"),
        AudioChannelMode.MONO: translate("Audio Mode", "Mono"),
    }


def subtitle_track_modes() -> dict:
    return {
        SubtitleTrackMode.DISABLED: translate("Subtitle Track", "Off"),
        SubtitleTrackMode.PREFERRED: translate("Subtitle Track", "Preferred Language"),
        SubtitleTrackMode.DEFAULT: translate("Subtitle Track", "Default"),
    }


def subtitle_encodings() -> dict:
    return {"": translate("Subtitle Encoding", "Default"), **SUBTITLE_ENCODINGS}


def audio_track_modes() -> dict:
    return {
        AudioTrackMode.DEFAULT: translate("Audio Track", "Default"),
        AudioTrackMode.PREFERRED: translate("Audio Track", "Preferred Language"),
        AudioTrackMode.DISABLED: translate("Audio Track", "Disable Audio"),
    }


def network_retry_modes() -> dict:
    return {
        NetworkRetryMode.OFF: translate("On Network Error", "Show error"),
        NetworkRetryMode.TIMES: translate("On Network Error", "Reload a few times"),
        NetworkRetryMode.INFINITE: translate("On Network Error", "Keep reloading"),
    }


def stream_qualities() -> dict:
    named = {
        "auto": translate("Stream Quality", "Auto (fit to pane)"),
        "best": translate("Stream Quality", "Best"),
        "best_audio_only": translate("Stream Quality", "Audio Only"),
    }
    codes = (
        "2160p",
        "2160p60",
        "1440p",
        "1440p60",
        "1080p",
        "1080p60",
        "720p60",
        "720p",
        "480p",
        "360p",
        "240p",
        "144p",
    )
    return {**named, **{code: code for code in codes}}


def font_families() -> dict:
    """Every font on this machine, with VLC's own pick at the top.

    Default is an empty name rather than a font, so that nothing is
    passed and VLC goes on choosing for itself.
    """

    families = QFontDatabase().families()

    return {
        "": translate("SettingsDialog", "Default"),
        **{family: family for family in families},
    }


def subtitle_outlines() -> dict:
    return {
        SubtitleOutline.NONE: translate("SettingsDialog", "None"),
        SubtitleOutline.THIN: translate("SettingsDialog", "Thin"),
        SubtitleOutline.NORMAL: translate("SettingsDialog", "Normal"),
        SubtitleOutline.THICK: translate("SettingsDialog", "Thick"),
    }


def color_schemes() -> dict:
    return {
        ColorScheme.SYSTEM: translate("SettingsDialog", "System"),
        ColorScheme.LIGHT: translate("SettingsDialog", "Light"),
        ColorScheme.DARK: translate("SettingsDialog", "Dark"),
    }


def cache_modes() -> dict:
    return {
        CacheMode.DISK: translate("SettingsDialog", "On disk"),
        CacheMode.MEMORY: translate("SettingsDialog", "In memory"),
    }


def screenshot_formats() -> dict:
    return {
        ScreenshotFormat.PNG: "PNG",
        ScreenshotFormat.JPG: "JPG",
    }


def url_resolvers() -> dict:
    return {
        URLResolver.STREAMLINK: "Streamlink",
        URLResolver.YT_DLP: "yt-dlp",
        URLResolver.DIRECT: translate("SettingsDialog", "Direct"),
    }


def proxy_modes() -> dict:
    return {
        ProxyMode.SYSTEM: translate("SettingsDialog", "System"),
        ProxyMode.NONE: translate("SettingsDialog", "None"),
        ProxyMode.CUSTOM: translate("SettingsDialog", "Custom"),
    }


def sponsorblock_modes(allowed: tuple[SponsorBlockMode, ...]) -> dict:
    names = {
        SponsorBlockMode.SKIP: translate("SettingsDialog", "Skip"),
        SponsorBlockMode.SHOW: translate("SettingsDialog", "Show in seek bar"),
        SponsorBlockMode.OFF: translate("SettingsDialog", "Disabled"),
    }

    return {mode: names[mode] for mode in allowed}


def video_drivers() -> dict:
    """The drivers this system has, and of those, the ones this session can
    run: where Hardware can't, its Software twin stands in for it."""

    # imported here, it asks the session, which is not there on import
    from gridplayer.utils.video_driver import (
        is_hw_video_available,
        session_video_driver,
    )

    # translate() kept out of the f-strings, where pylupdate5 cannot see it
    vlc_version = f" <VLC {env.VLC_VERSION}>"

    drivers = {}
    if not env.IS_MACOS:
        drivers[VideoDriver.VLC_HW] = (
            translate("SettingsDialog", "Hardware") + vlc_version
        )
    drivers.update(
        {
            VideoDriver.VLC_HW_SP: translate("SettingsDialog", "Hardware SP")
            + vlc_version,
            VideoDriver.VLC_SW: translate("SettingsDialog", "Software") + vlc_version,
            VideoDriver.VLC_SW_SP: translate("SettingsDialog", "Software SP")
            + vlc_version,
            VideoDriver.DUMMY: translate("SettingsDialog", "Dummy"),
        }
    )

    if is_hw_video_available():
        return drivers

    return {
        driver: name
        for driver, name in drivers.items()
        if session_video_driver(driver) == driver
    }


def hw_crop_borders() -> dict:
    return {
        HWCropBorderOffset.AUTO: translate("SettingsDialog", "Auto"),
        HWCropBorderOffset.DISABLED: translate("SettingsDialog", "Disabled"),
        HWCropBorderOffset.PX2: translate("SettingsDialog", "2 px"),
        HWCropBorderOffset.PX4: translate("SettingsDialog", "4 px"),
        HWCropBorderOffset.PX6: translate("SettingsDialog", "6 px"),
        HWCropBorderOffset.PX8: translate("SettingsDialog", "8 px"),
        HWCropBorderOffset.PX10: translate("SettingsDialog", "10 px"),
        HWCropBorderOffset.PX12: translate("SettingsDialog", "12 px"),
    }


def log_levels() -> dict:
    return {
        log_config.DISABLED: translate("ErrorLevel", "None"),
        logging.CRITICAL: translate("ErrorLevel", "Critical"),
        logging.ERROR: translate("ErrorLevel", "Error"),
        logging.WARNING: translate("ErrorLevel", "Warning"),
        logging.INFO: translate("ErrorLevel", "Info"),
        logging.DEBUG: translate("ErrorLevel", "Debug"),
    }


def vlc_log_levels() -> dict:
    return {
        log_config.DISABLED: translate("ErrorLevel", "None"),
        logging.ERROR: translate("ErrorLevel", "Error"),
        logging.WARNING: translate("ErrorLevel", "Warning"),
        logging.INFO: translate("ErrorLevel", "Info"),
        logging.DEBUG: translate("ErrorLevel", "Debug"),
    }
