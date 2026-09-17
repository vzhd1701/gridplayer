"""Pointing a DASH manifest back at the proxy.

A live manifest cannot be expanded into a segment list the way a recorded
one can: the list moves, and only the player knows when to ask for more.
So VLC is handed the manifest and follows it itself -- which means every
URL in it has to lead back here, or the segments would be fetched from
the host directly, without the cookies the manifest itself needed.
"""

import logging
import xml.etree.ElementTree as ET
from types import MappingProxyType
from urllib.parse import urljoin, urlsplit

MPD_NS = "urn:mpeg:dash:schema:mpd:2011"

# so the manifest comes back out with its own default namespace rather
# than the ns0: prefix ElementTree would invent for it
ET.register_namespace("", MPD_NS)

# where a URL sits other than in a BaseURL of its own; only the absolute
# ones are rewritten, because a relative one is resolved by the player
# against a BaseURL that has been rewritten already
URL_ATTRIBUTES = MappingProxyType(
    {
        "SegmentTemplate": ("media", "initialization", "index", "bitstreamSwitching"),
        "SegmentURL": ("media", "index"),
        "Initialization": ("sourceURL",),
        "RepresentationIndex": ("sourceURL",),
        "BitstreamSwitching": ("sourceURL",),
    }
)

_log = logging.getLogger(__name__)


def rewrite_manifest(manifest: str, manifest_url: str, proxify) -> str:
    """Hand back the manifest with every URL in it pointing at the proxy.

    `proxify` is given an absolute URL to serve as a base and answers
    with one of ours that stands for it.
    """

    root = ET.fromstring(manifest)

    base = _directory_of(manifest_url)

    _rewrite_element(root, base, proxify)

    _adopt_manifest_base(root, base, proxify)

    _drop_locations(root)

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _rewrite_element(element, base: str, proxify) -> None:
    """Rewrite one element of the manifest, then everything under it."""

    for attribute in URL_ATTRIBUTES.get(_tag_of(element), ()):
        _rewrite_attribute(element, attribute, proxify)

    base = _rewrite_bases(element, base, proxify)

    for child in element:
        # segment information can sit a level or two below the base it
        # belongs to, as a SegmentURL does under its SegmentList
        _rewrite_element(child, base, proxify)


def _rewrite_bases(element, base: str, proxify) -> str:
    """Point this level's bases at the proxy, and say what they resolve to.

    Several of them are alternatives for the same content, so they all
    get rewritten, and the first is the one the rest of the level is
    resolved against -- which is the one a player would settle on too.
    """

    base_urls = [child for child in element if _tag_of(child) == "BaseURL"]

    if not base_urls:
        return base

    resolved = urljoin(base, (base_urls[0].text or "").strip())

    for base_url in base_urls:
        base_url.text = proxify(urljoin(base, (base_url.text or "").strip()))

    return resolved


def _rewrite_attribute(element, attribute: str, proxify) -> None:
    url = element.get(attribute)

    if url is None or not _is_absolute(url):
        return

    element.set(attribute, _proxify_template(url, proxify))


def _proxify_template(template: str, proxify) -> str:
    """Replace the part of a template that is a URL, keeping the rest.

    What the player fills in is its business, so the proxy takes only the
    directory the placeholders sit under and leaves them where they are.
    """

    prefix, tail = _split_at_placeholder(template)

    return proxify(prefix) + tail


def _split_at_placeholder(template: str) -> tuple[str, str]:
    """The directory a template hangs off, and whatever hangs off it."""

    placeholder = template.find("$")

    end = len(template) if placeholder == -1 else placeholder

    cut = template.rfind("/", 0, end)

    return template[: cut + 1], template[cut + 1 :]


def _adopt_manifest_base(root, base: str, proxify) -> None:
    """Give a manifest with no base of its own the one it was fetched from.

    Without a BaseURL the player resolves against the URL the manifest
    came from, which is now a URL of ours that nothing hangs off.
    """

    if any(_tag_of(child) == "BaseURL" for child in root):
        return

    base_url = ET.Element(f"{{{MPD_NS}}}BaseURL")
    base_url.text = proxify(base)

    root.insert(_where_a_base_goes(root), base_url)


def _where_a_base_goes(root) -> int:
    """After the program information, which the schema puts first."""

    for position, child in enumerate(root):
        if _tag_of(child) != "ProgramInformation":
            return position

    return len(root)


def _drop_locations(root) -> None:
    """Take away the manifest's offer of somewhere else to be fetched from.

    A player that takes the offer would ask the host for the updates,
    where one left to itself keeps asking whoever served the manifest
    first, which is the proxy.
    """

    for location in [child for child in root if _tag_of(child) == "Location"]:
        _log.debug("Dropping a Location so manifest updates stay with us")

        root.remove(location)


def _directory_of(url: str) -> str:
    """What a relative URL in this document hangs off.

    A URL is not a path: Path() eats one of the slashes after the scheme,
    and on Windows turns what is left into a backslash.
    """

    return urljoin(url, ".")


def _is_absolute(url: str) -> bool:
    split = urlsplit(url)

    return bool(split.scheme or split.netloc)


def _tag_of(element) -> str:
    """The element's name without the namespace it is spelled in."""

    tag = element.tag

    if not isinstance(tag, str):
        # a comment or a processing instruction, whose tag is a callable
        return ""

    return tag.rpartition("}")[2]
