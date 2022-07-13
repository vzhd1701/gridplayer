import re
from enum import auto
from fnmatch import fnmatch
from typing import Iterable, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from gridplayer.params.static import AutoName, URLResolver


class ResolverPatternType(AutoName):
    WILDCARD_HOST = auto()
    WILDCARD_URL = auto()
    REGEX = auto()
    DISABLED = auto()


class ResolverPattern(BaseModel):
    pattern: str
    pattern_type: ResolverPatternType
    resolver: URLResolver

    def is_match(self, url: str):
        if self.pattern.strip() == "":
            return False

        if self.pattern_type == ResolverPatternType.WILDCARD_HOST:
            return self._match_wildcard_host(url)
        elif self.pattern_type == ResolverPatternType.WILDCARD_URL:
            return self._match_wildcard_url(url)
        elif self.pattern_type == ResolverPatternType.REGEX:
            return self._match_regex(url)

        return False

    def _match_wildcard_host(self, url: str) -> bool:
        hostname = urlparse(url).hostname

        if self.pattern.startswith("*."):
            return fnmatch(hostname, self.pattern) or fnmatch(
                hostname, self.pattern[2:]
            )

        if self.pattern.startswith("**."):
            return fnmatch(hostname, self.pattern[1:])

        return fnmatch(hostname, self.pattern)

    def _match_wildcard_url(self, url: str) -> bool:
        return fnmatch(url, self.pattern)

    def _match_regex(self, url: str) -> bool:
        return re.match(self.pattern, url) is not None


class ResolverPatterns(BaseModel):
    __root__: List[ResolverPattern]

    def __iter__(self) -> Iterable[ResolverPattern]:
        return iter(self.__root__)

    def get_resolver(self, url: str) -> Optional[URLResolver]:
        for pattern in self.__root__:
            if pattern.is_match(url):
                return pattern.resolver

        return None
