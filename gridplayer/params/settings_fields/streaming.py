from functools import partial

from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    ResolverPatternsField,
    SettingField,
    SpinField,
    TextField,
    When,
)
from gridplayer.params.sponsorblock import (
    CATEGORY_COLORS,
    ENABLED_SETTING,
    allowed_modes,
    category_name,
    category_setting,
)
from gridplayer.params.static import ProxyMode
from gridplayer.utils.qt import translate

# a request nobody is waiting on any more; longer than this and the
# video has given up on its own account
MAX_TIMEOUT_SEC = 600

STREAMING_FIELDS: tuple[SettingField, ...] = (
    CheckboxField(
        settings_key="streaming/hls_via_streamlink",
        label=translate(
            "SettingsDialog", "Use Streamlink for HLS streams when possible"
        ),
    ),
    ComboField(
        settings_key="streaming/resolver_priority",
        label=translate("SettingsDialog", "Priority URL resolver"),
        choices=choices.url_resolvers,
    ),
    TextField(
        settings_key="streaming/js_runtime_path",
        label=translate("SettingsDialog", "JavaScript runtime"),
        placeholder=translate("SettingsDialog", "Auto"),
        tooltip=translate(
            "SettingsDialog",
            "Folder holding deno, node, qjs or bun. Leave empty to search the usual"
            " places.",
        ),
    ),
    ResolverPatternsField(settings_key="streaming/resolver_priority_patterns"),
    CheckboxField(
        settings_key="cookies/enabled",
        label=translate("SettingsDialog", "Use stored cookies"),
        tooltip=translate(
            "SettingsDialog",
            "Send the stored cookies when resolving and streaming links",
        ),
    ),
    CheckboxField(
        settings_key="cookies/allow_update",
        label=translate("SettingsDialog", "Let yt-dlp refresh stored cookies"),
        tooltip=translate(
            "SettingsDialog",
            "Save new cookies that sites send while you watch. Keeps logins working"
            " longer, but rewrites the cookies file often.",
        ),
    ),
    ComboField(
        settings_key="network/proxy_mode",
        label=translate("SettingsDialog", "Proxy"),
        choices=choices.proxy_modes,
        tooltip=translate(
            "SettingsDialog",
            "System: use your computer's proxy settings.\n"
            "None: connect directly.\n"
            "Custom: use the proxy address you enter.",
        ),
    ),
    TextField(
        settings_key="network/proxy_url",
        label=translate("SettingsDialog", "Proxy address"),
        placeholder="http://host:port, socks5h://host:port",
        # only a proxy of the user's own has an address to type
        enabled_when=When("network/proxy_mode", (ProxyMode.CUSTOM,)),
    ),
    SpinField(
        settings_key="network/timeout",
        label=translate("SettingsDialog", "Request timeout"),
        minimum=0,
        maximum=MAX_TIMEOUT_SEC,
        special_text=translate("SettingsDialog", "Auto"),
        suffix=translate("SettingsDialog", "(sec)"),
        tooltip=translate(
            "SettingsDialog",
            "How long to wait for a site to answer while opening a link. Doesn't"
            " affect playback.",
        ),
    ),
    TextField(
        settings_key="network/user_agent",
        label=translate("SettingsDialog", "User agent"),
        placeholder=translate("SettingsDialog", "Auto"),
        tooltip=translate(
            "SettingsDialog",
            "How the player identifies itself to sites. Leave empty for the default.",
        ),
    ),
    CheckboxField(
        settings_key="network/force_ipv4",
        label=translate("SettingsDialog", "Force IPv4"),
        tooltip=translate(
            "SettingsDialog",
            "Connect over IPv4 only. Try this if links stall or a site blocks your"
            " IPv6 address.",
        ),
    ),
    CheckboxField(
        settings_key="network/verify_tls",
        label=translate("SettingsDialog", "Verify TLS certificates"),
        tooltip=translate(
            "SettingsDialog",
            "Turn this off only for a proxy that signs traffic with its own"
            " certificate",
        ),
    ),
    CheckboxField(
        settings_key="network/allow_http_in_playlists",
        label=translate("SettingsDialog", "Allow http links in https playlists"),
        tooltip=translate(
            "SettingsDialog",
            "Some streams have an https playlist that links to http video. Turn this"
            " off to block those links.",
        ),
    ),
)

# a row for each category there is, from the one list the seek bar goes by
# too, so that a category is added in one place
SPONSORBLOCK_FIELDS: tuple[SettingField, ...] = (
    CheckboxField(
        settings_key=ENABLED_SETTING,
        label=translate("SettingsDialog", "Use SponsorBlock on YouTube videos"),
    ),
    *(
        ComboField(
            settings_key=category_setting(category),
            label=category_name(category),
            swatch=color,
            choices=partial(choices.sponsorblock_modes, allowed_modes(category)),
            enabled_when=When(ENABLED_SETTING),
        )
        for category, color in CATEGORY_COLORS.items()
    ),
)
