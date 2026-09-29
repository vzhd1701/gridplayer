"""SponsorBlock's categories, as the settings and the seek bar know them.

SponsorBlock is a database of the parts of YouTube videos that its users have
marked as a sponsor read, a plug for the channel, an intro and the like. Each
kind is skipped, shown on the seek bar, or left alone, as the settings say.

The colours are the browser extension's own, so that a stretch looks here the
way it does on YouTube to anyone who has it installed.
"""

from types import MappingProxyType

from gridplayer.params.static import SponsorBlockMode
from gridplayer.utils.qt import translate

# the point SponsorBlock's users picked as the one worth seeing, which is a
# place to be rather than a stretch to pass over
HIGHLIGHT_CATEGORY = "poi_highlight"

# in the order the settings list them, which is the extension's
CATEGORY_COLORS = MappingProxyType(
    {
        "sponsor": "#00d400",
        "selfpromo": "#ffff00",
        "interaction": "#cc00ff",
        "intro": "#00ffff",
        "outro": "#0202ed",
        "preview": "#008fd6",
        "hook": "#395699",
        "filler": "#7300ff",
        "music_offtopic": "#ff9900",
        HIGHLIGHT_CATEGORY: "#ff1684",
    }
)

ENABLED_SETTING = "sponsorblock/enabled"


def category_setting(category: str) -> str:
    """The setting for what becomes of a category; see gridplayer.settings."""

    return f"sponsorblock/{category}"


# every setting there is for it, to tell when any of them has changed
SPONSORBLOCK_SETTINGS = (
    ENABLED_SETTING,
    *(category_setting(category) for category in CATEGORY_COLORS),
)


def allowed_modes(category: str) -> tuple[SponsorBlockMode, ...]:
    """What a category can be set to: a highlight is a point, with no length
    to skip."""

    if category == HIGHLIGHT_CATEGORY:
        return SponsorBlockMode.SHOW, SponsorBlockMode.OFF

    return tuple(SponsorBlockMode)


def category_name(category: str) -> str:
    """What SponsorBlock calls a category, in the words of the extension."""

    names = {
        "sponsor": translate("SponsorBlock", "Sponsor"),
        "selfpromo": translate("SponsorBlock", "Unpaid/Self Promotion"),
        "interaction": translate("SponsorBlock", "Interaction Reminder"),
        "intro": translate("SponsorBlock", "Intermission/Intro Animation"),
        "outro": translate("SponsorBlock", "Endcards/Credits"),
        "preview": translate("SponsorBlock", "Preview/Recap"),
        "hook": translate("SponsorBlock", "Hook/Greetings"),
        "filler": translate("SponsorBlock", "Filler Tangent"),
        "music_offtopic": translate("SponsorBlock", "Non-Music Section"),
        HIGHLIGHT_CATEGORY: translate("SponsorBlock", "Highlight"),
    }

    return names.get(category, category)
