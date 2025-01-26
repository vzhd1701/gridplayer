import random
from pathlib import Path
from typing import Optional, List

from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT


class VideoNavigator:
    def __init__(self, start_file: Path, is_shuffle: bool = False):
        self.original_dir = start_file.parent
        self.siblings = get_file_siblings(self.original_dir)
        if is_shuffle:
            random.shuffle(self.siblings)
        self.current_index = self.siblings.index(start_file) if start_file in self.siblings else -1

    def next_video_file(self) -> Optional[Path]:
        if not self.siblings or self.current_index == -1:
            return None
        self.current_index = (self.current_index + 1) % len(self.siblings)
        return self.siblings[self.current_index]

    def previous_video_file(self) -> Optional[Path]:
        if not self.siblings or self.current_index == -1:
            return None
        self.current_index = (self.current_index - 1) % len(self.siblings)
        return self.siblings[self.current_index]

def get_file_siblings(directory: Path):

    return sorted(
        f
        for f in directory.rglob("*")  # Recursively includes subdirectories
        if f.is_file() and f.suffix[1:].lower() in SUPPORTED_MEDIA_EXT
    )
