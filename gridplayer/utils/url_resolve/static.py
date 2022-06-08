import re
from dataclasses import dataclass
from typing import Dict

YOUTUBE_MATCH = re.compile(r"^(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)")


class BadURLException(Exception):
    """Exception for bad URLs"""


class NoResolverPlugin(Exception):
    """Exception for no resolver plugin"""


@dataclass
class ResolvedVideo(object):
    title: str
    urls: Dict[str, str]
    is_live: bool
