"""The loop of a video block: the stretch of it played over and over, and
whether each pass starts somewhere at random.

Where a loop ends up taking the video is the block's (see loop_start,
loop_end and time_changed); here is only how the viewer sets it.
"""

from gridplayer.widgets.video_block_guards import VideoBlockPart, only_seekable


class LoopControl(VideoBlockPart):
    @only_seekable
    def toggle_random(self):
        self.set_random(not self._block.video_params.is_start_random)

    def set_random(self, is_start_random: bool):
        """Start each pass somewhere at random, or where the loop starts.

        Kept for a video stopped or still loading too, which goes by it
        once it plays, and for one that is live, which never loops.
        """

        self._block.video_params.is_start_random = is_start_random

    @only_seekable
    def set_start(self):
        self.set_start_time(self._block.time)

    @only_seekable
    def set_start_time(self, new_time):
        if None not in {self._block.video_params.loop_end, new_time}:
            if new_time >= self._block.video_params.loop_end:
                return

        self._block.video_params.loop_start = new_time

        if new_time is None:
            self._block.loop_start_change.emit(0)
        else:
            self._block.loop_start_change.emit(
                new_time / self._block.video_driver.length
            )

    @only_seekable
    def set_end(self):
        self.set_end_time(self._block.time)

    @only_seekable
    def set_end_time(self, new_time):
        if None not in {self._block.video_params.loop_start, new_time}:
            if new_time <= self._block.video_params.loop_start:
                return

        self._block.video_params.loop_end = new_time

        if new_time is None:
            self._block.loop_end_change.emit(100.0)
        else:
            self._block.loop_end_change.emit(new_time / self._block.video_driver.length)

    @only_seekable
    def reset(self):
        self.set_start_time(None)
        self.set_end_time(None)
