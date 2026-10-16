from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ColorField,
    ComboField,
    CropField,
    FloatSpinField,
    SettingField,
    SpinField,
    TextField,
    When,
)
from gridplayer.params.static import (
    MAX_LIST_FAIL_WAIT_SEC,
    MAX_RATE,
    MAX_SCALE,
    MIN_RATE,
    MIN_SCALE,
    AudioTrackMode,
    ListFailAction,
    NetworkRetryMode,
    SubtitleTrackMode,
    VideoDeinterlace,
)
from gridplayer.utils.qt import translate

VIDEO_FIELDS: tuple[SettingField, ...] = (
    ColorField(
        settings_key="video_defaults/color",
        label=translate("SettingsDialog", "Overlay color"),
    ),
    ComboField(
        settings_key="video_defaults/audio_track_mode",
        label=translate("SettingsDialog", "Audio track"),
        choices=choices.audio_track_modes,
        tooltip=translate(
            "SettingsDialog",
            "Which audio track to start with: the file's default, one in your"
            " preferred languages, or none (no audio decoded, which isn't the same as"
            " muted).",
        ),
    ),
    TextField(
        settings_key="video_defaults/audio_languages",
        label=translate("SettingsDialog", "Languages"),
        placeholder=translate("SettingsDialog", "en, ja, fr"),
        enabled_when=When(
            "video_defaults/audio_track_mode", (AudioTrackMode.PREFERRED,)
        ),
        tooltip=translate(
            "SettingsDialog",
            "Language codes or names, best first."
            " Videos that offer none of them keep their own default track.",
        ),
    ),
    CheckboxField(
        settings_key="video_defaults/external_audio_autodiscover",
        label=translate("SettingsDialog", "Detect external audio files"),
        tooltip=translate(
            "SettingsDialog",
            "Offer audio files next to the video with the same name. They're opened"
            " only when you pick one.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/audio_mode",
        label=translate("SettingsDialog", "Audio mode"),
        choices=choices.audio_modes,
    ),
    FloatSpinField(
        settings_key="video_defaults/volume",
        label=translate("SettingsDialog", "Volume"),
        minimum=0,
        maximum=1,
        decimals=2,
        step=0.05,
    ),
    CheckboxField(
        settings_key="video_defaults/muted",
        label=translate("SettingsDialog", "Muted"),
    ),
    ComboField(
        settings_key="video_defaults/subtitle_track_mode",
        label=translate("SettingsDialog", "Subtitles"),
        choices=choices.subtitle_track_modes,
        tooltip=translate(
            "SettingsDialog",
            "Which subtitles to start with: none, ones in your preferred languages,"
            " or the file's default.",
        ),
    ),
    TextField(
        settings_key="video_defaults/subtitle_languages",
        label=translate("SettingsDialog", "Languages"),
        placeholder=translate("SettingsDialog", "en, ja, fr"),
        enabled_when=When(
            "video_defaults/subtitle_track_mode", (SubtitleTrackMode.PREFERRED,)
        ),
        tooltip=translate(
            "SettingsDialog",
            "Language codes or names, best first."
            " Videos that offer none of them are shown without subtitles.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/subtitle_encoding",
        label=translate("SettingsDialog", "Text encoding"),
        choices=choices.subtitle_encodings,
        tooltip=translate(
            "SettingsDialog",
            "Encoding for subtitle files that aren't UTF-8. UTF-8 is detected"
            " automatically. Doesn't affect ASS and SSA subtitles.",
        ),
    ),
    CheckboxField(
        settings_key="video_defaults/external_subtitle_autodiscover",
        label=translate("SettingsDialog", "Detect external subtitle files"),
        tooltip=translate(
            "SettingsDialog",
            "Offer subtitle files next to the video with the same name. They're"
            " opened only when you pick one.",
        ),
    ),
    FloatSpinField(
        settings_key="video_defaults/scale",
        label=translate("SettingsDialog", "Zoom"),
        minimum=MIN_SCALE,
        maximum=MAX_SCALE,
        decimals=1,
        step=0.1,
    ),
    CheckboxField(
        settings_key="video_defaults/zoom_to_cursor",
        label=translate("Zoom", "Zoom to cursor"),
        tooltip=translate(
            "SettingsDialog",
            "Zoom toward the mouse pointer instead of the alignment point. Resetting"
            " the zoom also recenters the picture.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/aspect",
        label=translate("SettingsDialog", "Aspect mode"),
        choices=choices.aspects,
    ),
    CropField(
        settings_key="video_defaults/crop",
        label=translate("SettingsDialog", "Crop"),
    ),
    ComboField(
        settings_key="video_defaults/anchor",
        label=translate("SettingsDialog", "Alignment"),
        choices=choices.anchors,
    ),
    CheckboxField(
        settings_key="video_defaults/shift_past_edges",
        label=translate("SettingsDialog", "Allow moving past the edges"),
    ),
    ComboField(
        settings_key="video_defaults/transform",
        label=translate("SettingsDialog", "Transform"),
        choices=choices.transforms,
    ),
    ComboField(
        settings_key="video_defaults/deinterlace",
        label=translate("SettingsDialog", "Deinterlace"),
        choices=choices.deinterlace_states,
        tooltip=translate(
            "SettingsDialog",
            "Automatic: only videos marked as interlaced.\n"
            "On: always. Use it if you see combing on moving edges.\n"
            "Off: never.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/deinterlace_mode",
        label=translate("SettingsDialog", "Mode"),
        choices=choices.deinterlace_modes,
        enabled_when=When(
            "video_defaults/deinterlace", (VideoDeinterlace.AUTO, VideoDeinterlace.ON)
        ),
        tooltip=translate(
            "SettingsDialog",
            "Auto: VLC chooses (currently X).\n"
            "Yadif (2x), Bob and Phosphor double the frame rate, which costs more"
            " with many videos.\n"
            "With hardware decoding, the GPU may use another mode it supports.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/end_action",
        label=translate("SettingsDialog", "When finished"),
        choices=choices.end_actions,
    ),
    CheckboxField(
        settings_key="video_defaults/dir_recursive",
        label=translate("Folder Navigation", "Include subfolders"),
        tooltip=translate(
            "Folder Navigation",
            "Next, previous and random files also come from subfolders.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/list_end_action",
        label=translate("Lists", "When list ends"),
        choices=choices.list_end_actions,
        tooltip=translate(
            "Lists",
            "What a cell playing a list does after the last item.",
        ),
    ),
    ComboField(
        settings_key="video_defaults/list_fail_action",
        label=translate("When Video Fails", "When video fails"),
        choices=choices.list_fail_actions,
        tooltip=translate(
            "When Video Fails",
            "For cells playing a list. Play next doesn't reload a video"
            " that's gone or refused.",
        ),
    ),
    SpinField(
        settings_key="video_defaults/list_fail_wait",
        label=translate("When Video Fails", "Next after"),
        minimum=0,
        maximum=MAX_LIST_FAIL_WAIT_SEC,
        special_text=translate("When Video Fails", "At once"),
        suffix=translate("SettingsDialog", "(sec)"),
        enabled_when=When(
            "video_defaults/list_fail_action", (ListFailAction.PLAY_NEXT,)
        ),
    ),
    CheckboxField(
        settings_key="video_defaults/random_loop",
        label=translate("SettingsDialog", "Start at random position"),
    ),
    ComboField(
        settings_key="video_defaults/initial_state",
        label=translate("SettingsDialog", "Initial state"),
        choices=choices.initial_states,
    ),
    FloatSpinField(
        settings_key="video_defaults/rate",
        label=translate("SettingsDialog", "Playback speed"),
        minimum=MIN_RATE,
        maximum=MAX_RATE,
        decimals=2,
        step=0.1,
    ),
    ComboField(
        settings_key="video_defaults/stream_quality",
        label=translate("SettingsDialog", "Stream quality"),
        choices=choices.stream_qualities,
    ),
    SpinField(
        settings_key="video_defaults/quality_adapt_delay",
        label=translate("SettingsDialog", "Adapt after"),
        minimum=1,
        maximum=3600,
        suffix=translate("SettingsDialog", "(sec)"),
        enabled_when=When("video_defaults/stream_quality", ("auto",)),
        tooltip=translate(
            "SettingsDialog",
            "How long a video must keep its new size before Auto quality adjusts",
        ),
    ),
    ComboField(
        settings_key="video_defaults/network_retry_mode",
        label=translate("SettingsDialog", "On network error"),
        choices=choices.network_retry_modes,
    ),
    SpinField(
        settings_key="video_defaults/network_retry_times",
        label=translate("SettingsDialog", "Attempts"),
        minimum=1,
        maximum=1000,
        enabled_when=When(
            "video_defaults/network_retry_mode", (NetworkRetryMode.TIMES,)
        ),
    ),
    SpinField(
        settings_key="video_defaults/auto_reload_timer",
        label=translate("SettingsDialog", "Auto reload time"),
        minimum=0,
        maximum=1000,
        special_text=translate("SettingsDialog", "Disabled"),
        suffix=translate("SettingsDialog", "(min)"),
    ),
)
