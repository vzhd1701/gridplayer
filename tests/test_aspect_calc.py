import math
import random

import pytest

from gridplayer.params.static import (
    VideoAnchor,
    VideoAspect,
    VideoCrop,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.utils.aspect_calc import (
    calc_crop_region,
    calc_moved_shift,
    calc_view_borders,
    calc_view_geometry,
    calc_view_placement,
    calc_view_shift,
    calc_view_step,
    calc_whole_geometry,
    calc_whole_placement,
)

VIDEO = (1920, 1080)
PANE = (1600, 900)
SQUARE = (900, 900)
NO_CROP = VideoCrop(0, 0, 0, 0)
NO_SHIFT = VideoShift(0, 0)


def _view(
    aspect=VideoAspect.FIT,
    scale=1.0,
    crop=NO_CROP,
    anchor=VideoAnchor.CENTER,
    shift=NO_SHIFT,
    is_shift_past_edges=False,
):
    return ViewParams(aspect, scale, crop, anchor, shift, is_shift_past_edges)


def _approx(rect):
    return pytest.approx(rect, abs=1e-6)


def _shown_ratio(override, frame, borders):
    """The shape VLC gives the cropped region, from what it is told.

    sar = A_num * vid_y : A_den * vid_x, and the region is shown with
    DAR = region_x * sar_num : region_y * sar_den.
    """
    num, den = (int(part) for part in override.split(":"))
    _, _, region_x, region_y = calc_crop_region(frame, borders)

    return (region_x * num * frame[1]) / (region_y * den * frame[0])


def _fits_vlc(override, frame, borders):
    """Whether VLC 3's 32-bit unsigned sums on the override come out right.

    It makes the SAR num * frame_h : den * frame_w and reduces it, then
    places the picture multiplying its terms by the cropped region's sides.
    """

    num, den = (int(part) for part in override.split(":"))
    frame_w, frame_h = frame
    _, _, region_w, region_h = calc_crop_region(frame, borders)

    sar_num, sar_den = num * frame_h, den * frame_w
    shared = math.gcd(sar_num, sar_den)
    sar_num, sar_den = sar_num // shared, sar_den // shared

    return all(
        product < 1 << 32
        for product in (
            num * frame_h,
            den * frame_w,
            region_w * sar_num,
            region_h * sar_den,
            region_h * sar_num,
            region_w * sar_den,
        )
    )


def _borders(geometry):
    return VideoCrop(*(int(part) for part in geometry.split("+")[1:]))


class TestPlacementFit:
    def test_same_shape_fills_the_pane_with_all_of_it(self):
        placement = calc_view_placement(VIDEO, PANE, _view())

        assert placement.source == _approx((0, 0, 1920, 1080))
        assert placement.target == _approx((0, 0, 1600, 900))

    def test_covers_a_square_pane_from_the_middle(self):
        placement = calc_view_placement(VIDEO, SQUARE, _view())

        assert placement.source == _approx((420, 0, 1080, 1080))
        assert placement.target == _approx((0, 0, 900, 900))

    @pytest.mark.parametrize(
        ("anchor", "source_x"),
        [
            (VideoAnchor.LEFT, 0),
            (VideoAnchor.TOP_LEFT, 0),
            (VideoAnchor.BOTTOM_LEFT, 0),
            (VideoAnchor.CENTER, 420),
            (VideoAnchor.TOP, 420),
            (VideoAnchor.BOTTOM, 420),
            (VideoAnchor.RIGHT, 840),
            (VideoAnchor.TOP_RIGHT, 840),
            (VideoAnchor.BOTTOM_RIGHT, 840),
        ],
    )
    def test_the_anchor_picks_what_is_cut_off(self, anchor, source_x):
        # a wide picture in a square pane has room to move across only
        placement = calc_view_placement(VIDEO, SQUARE, _view(anchor=anchor))

        assert placement.source == _approx((source_x, 0, 1080, 1080))
        assert placement.target == _approx((0, 0, 900, 900))

    def test_the_shift_moves_the_picture(self):
        # the picture moves 100 frame pixels left, so 100 more of its right
        placement = calc_view_placement(VIDEO, SQUARE, _view(shift=VideoShift(-100, 0)))

        assert placement.source == _approx((520, 0, 1080, 1080))

    def test_the_shift_is_counted_from_the_anchor(self):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(anchor=VideoAnchor.LEFT, shift=VideoShift(-100, 0))
        )

        assert placement.source == _approx((100, 0, 1080, 1080))

    @pytest.mark.parametrize("shift", [VideoShift(5000, 0), VideoShift(-5000, 0)])
    def test_the_shift_stops_at_the_edges(self, shift):
        placement = calc_view_placement(VIDEO, SQUARE, _view(shift=shift))

        source_x = 0 if shift.X > 0 else 840
        assert placement.source == _approx((source_x, 0, 1080, 1080))
        assert placement.target == _approx((0, 0, 900, 900))

    def test_the_shift_is_held_on_an_axis_with_no_room(self):
        placement = calc_view_placement(VIDEO, SQUARE, _view(shift=VideoShift(0, 50)))

        assert placement.source == _approx((420, 0, 1080, 1080))

    def test_the_user_crop_is_covered_from_its_middle(self):
        # 960x1080 left, 16:9 of it is 960x540
        placement = calc_view_placement(
            VIDEO, PANE, _view(crop=VideoCrop(480, 0, 480, 0))
        )

        assert placement.source == _approx((480, 270, 960, 540))


class TestPlacementZoom:
    def test_zooms_about_the_middle(self):
        placement = calc_view_placement(VIDEO, PANE, _view(scale=2.0))

        assert placement.source == _approx((480, 270, 960, 540))
        assert placement.target == _approx((0, 0, 1600, 900))

    def test_zooms_about_the_anchor(self):
        placement = calc_view_placement(
            VIDEO, PANE, _view(scale=2.0, anchor=VideoAnchor.BOTTOM_RIGHT)
        )

        assert placement.source == _approx((960, 540, 960, 540))

    def test_pans_across_the_zoomed_picture(self):
        placement = calc_view_placement(
            VIDEO, PANE, _view(scale=2.0, shift=VideoShift(-200, 100))
        )

        assert placement.source == _approx((680, 170, 960, 540))

    def test_none_is_cut_only_where_it_outgrows_the_pane(self):
        # fitted inside a square pane it is 900x506.25, zoomed 1800x1012.5
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(VideoAspect.NONE, scale=2.0)
        )

        assert placement.target == _approx((0, 0, 900, 900))
        assert placement.source == _approx((480, 60, 960, 960))

    def test_none_keeps_letterbox_while_it_fits(self):
        placement = calc_view_placement(
            VIDEO, (900, 2000), _view(VideoAspect.NONE, scale=1.5)
        )

        # 900x506.25 fitted, 1350x759.375 zoomed
        assert placement.target == _approx((0, (2000 - 759.375) / 2, 900, 759.375))
        assert placement.source == _approx((320, 0, 1280, 1080))


class TestPlacementNoneAndStretch:
    def test_none_letterboxes_in_the_middle(self):
        placement = calc_view_placement(VIDEO, SQUARE, _view(VideoAspect.NONE))

        assert placement.source == _approx((0, 0, 1920, 1080))
        assert placement.target == _approx((0, (900 - 506.25) / 2, 900, 506.25))

    @pytest.mark.parametrize(
        ("anchor", "top"),
        [
            (VideoAnchor.TOP, 0),
            (VideoAnchor.BOTTOM, 900 - 506.25),
            (VideoAnchor.LEFT, (900 - 506.25) / 2),
        ],
    )
    def test_none_stands_where_the_anchor_says(self, anchor, top):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(VideoAspect.NONE, anchor=anchor)
        )

        assert placement.target == _approx((0, top, 900, 506.25))

    def test_none_is_kept_whole_inside_the_pane(self):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(VideoAspect.NONE, shift=VideoShift(0, -2000))
        )

        assert placement.target == _approx((0, 0, 900, 506.25))

    @pytest.mark.parametrize("anchor", list(VideoAnchor))
    def test_stretch_has_no_room_to_move(self, anchor):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(VideoAspect.STRETCH, anchor=anchor)
        )

        assert placement.source == _approx((0, 0, 1920, 1080))
        assert placement.target == _approx((0, 0, 900, 900))

    def test_stretch_zoomed_can_pan(self):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(VideoAspect.STRETCH, scale=2.0, anchor=VideoAnchor.TOP)
        )

        assert placement.source == _approx((480, 0, 960, 540))


class TestPlacementRotation:
    """VLC keeps a rotated frame at its unrotated size, the picture squeezed."""

    FRAME = (640, 360)

    def test_fills_a_pane_of_its_turned_shape(self):
        placement = calc_view_placement(
            self.FRAME, (360, 640), _view(), VideoTransform.ROTATE_90
        )

        assert placement.source == _approx((0, 0, 640, 360))
        assert placement.target == _approx((0, 0, 360, 640))

    def test_covers_a_wide_pane_with_a_band_of_it(self):
        # shown 360x640, a 640x360 pane takes 360x202.5 of it: a band
        # 202.5/640 of the frame's height, which is its width turned
        placement = calc_view_placement(
            self.FRAME, (640, 360), _view(), VideoTransform.TRANSPOSE
        )

        band = 360 * 202.5 / 640
        assert placement.source == _approx((0, (360 - band) / 2, 640, band))

    def test_letterboxes_in_its_turned_shape(self):
        placement = calc_view_placement(
            self.FRAME, (640, 360), _view(VideoAspect.NONE), VideoTransform.ROTATE_270
        )

        # 360 tall, so 202.5 wide
        assert placement.target == _approx(((640 - 202.5) / 2, 0, 202.5, 360))

    def test_a_crop_takes_from_the_side_it_is_named_for(self):
        # Left 160 of the 640 frame pixels across is a quarter of the width
        # on screen, whichever way the picture was turned
        placement = calc_view_placement(
            self.FRAME,
            (360, 640),
            _view(VideoAspect.NONE, crop=VideoCrop(160, 0, 0, 0)),
            VideoTransform.ROTATE_90,
        )

        assert placement.source == _approx((160, 0, 480, 360))
        assert placement.target == _approx((45, 0, 270, 640))

    @pytest.mark.parametrize(
        "transform",
        [
            VideoTransform.ROTATE_180,
            VideoTransform.HFLIP,
            VideoTransform.VFLIP,
            VideoTransform.NONE,
            None,
        ],
    )
    def test_other_transforms_keep_the_shape(self, transform):
        placement = calc_view_placement(
            self.FRAME, (640, 360), _view(), transform=transform
        )

        assert placement.source == _approx((0, 0, 640, 360))


class TestShiftHeldAtTheEdges:
    """Where a move starts from: the shift the picture really stands at."""

    def test_within_the_edges_it_is_as_asked(self):
        view = _view(shift=VideoShift(-100, 0))

        assert calc_view_shift(VIDEO, SQUARE, view) == VideoShift(-100, 0)

    @pytest.mark.parametrize(
        ("shift", "held"),
        [
            # 700 pane pixels of room across, 840 frame pixels, half each way
            (VideoShift(5000, 50), VideoShift(420, 0)),
            (VideoShift(-5000, -50), VideoShift(-420, 0)),
        ],
    )
    def test_past_an_edge_it_is_where_the_picture_stops(self, shift, held):
        assert calc_view_shift(VIDEO, SQUARE, _view(shift=shift)) == held

    @pytest.mark.parametrize(
        ("shift", "held"),
        [
            (VideoShift(300, 0), VideoShift(0, 0)),
            (VideoShift(-5000, 0), VideoShift(-840, 0)),
        ],
    )
    def test_it_is_counted_from_the_anchor(self, shift, held):
        """Against the left edge the picture can only go left."""

        view = _view(anchor=VideoAnchor.LEFT, shift=shift)

        assert calc_view_shift(VIDEO, SQUARE, view) == held

    def test_a_smaller_picture_moves_about_inside_the_pane(self):
        # 900x506.25 in a 900x900 pane, 420 frame pixels of room up or down
        view = _view(VideoAspect.NONE, shift=VideoShift(10, 1000))

        assert calc_view_shift(VIDEO, SQUARE, view) == VideoShift(0, 420)

    def test_nothing_to_work_from_leaves_it_as_it_is(self):
        view = _view(shift=VideoShift(5000, 0))

        assert calc_view_shift((0, 0), SQUARE, view) == VideoShift(5000, 0)


class TestPastTheEdges:
    """Where the picture may go when it is let past the pane's edges."""

    def test_shows_black_where_the_picture_has_gone_from(self):
        # 100 frame pixels is 100 * 900/1080 pane pixels
        view = _view(
            anchor=VideoAnchor.LEFT, shift=VideoShift(100, 0), is_shift_past_edges=True
        )

        placement = calc_view_placement(VIDEO, SQUARE, view)

        assert placement.target == _approx((250 / 3, 0, 900 - 250 / 3, 900))
        assert placement.source == _approx((0, 0, 980, 1080))

    def test_a_bigger_picture_goes_as_far_as_the_middle_of_the_pane(self):
        # zoomed to 3200x1800 in 1600x900, 5/3 pane pixels to a frame pixel
        view = _view(scale=2.0, shift=VideoShift(5000, 0), is_shift_past_edges=True)

        placement = calc_view_placement(VIDEO, PANE, view)

        assert placement.target == _approx((800, 0, 800, 900))
        assert placement.source == _approx((0, 270, 480, 540))

    def test_a_smaller_picture_goes_as_far_as_half_of_it_out(self):
        # 900x506.25 in a 900x900 pane, pulled up half out of it
        view = _view(
            VideoAspect.NONE, shift=VideoShift(0, -5000), is_shift_past_edges=True
        )

        placement = calc_view_placement(VIDEO, SQUARE, view)

        assert placement.target == _approx((0, 0, 900, 253.125))
        assert placement.source == _approx((0, 540, 1920, 540))

    @pytest.mark.parametrize(
        "view",
        [
            _view(shift=VideoShift(-300, 0)),
            _view(anchor=VideoAnchor.LEFT, shift=VideoShift(-500, 0)),
            _view(VideoAspect.NONE, shift=VideoShift(0, 200)),
            _view(VideoAspect.NONE, scale=3.0, shift=VideoShift(400, -100)),
        ],
    )
    def test_within_the_edges_it_goes_where_it_would_anyway(self, view):
        allowed = view._replace(is_shift_past_edges=True)

        assert calc_view_placement(VIDEO, SQUARE, allowed) == calc_view_placement(
            VIDEO, SQUARE, view
        )

    def test_the_shift_is_held_where_the_picture_stops(self):
        # 0.46875 pane pixels to a frame pixel, 196.875 above the picture
        # at the anchor and 253.125 of it to take out of the pane
        view = _view(
            VideoAspect.NONE, shift=VideoShift(0, -5000), is_shift_past_edges=True
        )

        assert calc_view_shift(VIDEO, SQUARE, view) == VideoShift(0, -960)

    def test_it_is_held_within_the_edges_again_once_not_let_past(self):
        view = _view(VideoAspect.NONE, shift=VideoShift(0, -960))

        assert calc_view_shift(VIDEO, SQUARE, view) == VideoShift(0, -420)

    def test_is_never_clear_of_the_pane(self):
        view = _view(
            scale=10.0, shift=VideoShift(-99999, 99999), is_shift_past_edges=True
        )

        placement = calc_view_placement(VIDEO, SQUARE, view)

        assert placement.target == _approx((0, 450, 450, 450))


class TestWholePlacement:
    """All of a frame VLC turns as it shows it, to be cut to the view."""

    def test_is_all_of_the_picture_where_it_goes(self):
        # 1600x900, half of the 700 it is too wide by off each side
        placement = calc_whole_placement(VIDEO, SQUARE, _view())

        assert placement.source == _approx((0, 0, 1920, 1080))
        assert placement.target == _approx((-350, 0, 1600, 900))

    @pytest.mark.parametrize(
        "view",
        [
            _view(anchor=VideoAnchor.RIGHT),
            _view(scale=2.0, anchor=VideoAnchor.TOP_LEFT, shift=VideoShift(-90, 40)),
            _view(
                VideoAspect.NONE, shift=VideoShift(0, -5000), is_shift_past_edges=True
            ),
            _view(scale=3.0, shift=VideoShift(5000, 5000), is_shift_past_edges=True),
            _view(VideoAspect.STRETCH, scale=1.5, anchor=VideoAnchor.BOTTOM),
        ],
    )
    def test_the_pane_cuts_it_down_to_the_view(self, view):
        whole = calc_whole_placement(VIDEO, PANE, view)
        shown = calc_view_placement(VIDEO, PANE, view)

        x, y, width, height = whole.target
        left, top = max(x, 0), max(y, 0)
        right, bottom = min(x + width, PANE[0]), min(y + height, PANE[1])

        assert (left, top, right - left, bottom - top) == _approx(shown.target)

    def test_a_crop_of_the_users_is_drawn_too(self):
        # 1600x1080 left of it covers the square at 1333x900, centred, and
        # the 320 cut off the left is 267 more to the left of that
        view = _view(crop=VideoCrop(320, 0, 0, 0))

        placement = calc_whole_placement(VIDEO, SQUARE, view)

        assert placement.source == _approx((0, 0, 1920, 1080))
        assert placement.target == _approx((-1450 / 3, 0, 1600, 900))

    @pytest.mark.parametrize(
        "view",
        [
            _view(crop=VideoCrop(320, 0, 0, 0)),
            _view(crop=VideoCrop(100, 200, 300, 50), anchor=VideoAnchor.TOP_LEFT),
            _view(VideoAspect.NONE, crop=VideoCrop(0, 300, 900, 0)),
            _view(
                VideoAspect.NONE,
                crop=VideoCrop(500, 0, 0, 400),
                shift=VideoShift(0, -5000),
                is_shift_past_edges=True,
            ),
            _view(scale=2.5, crop=VideoCrop(40, 30, 20, 10), shift=VideoShift(90, 40)),
        ],
    )
    def test_the_part_the_crop_keeps_is_where_the_view_has_it(self, view):
        whole = calc_whole_placement(VIDEO, PANE, view)
        shown = calc_view_placement(VIDEO, PANE, view)

        x, y, width, height = whole.target
        per_x, per_y = width / VIDEO[0], height / VIDEO[1]
        crop = view.crop
        kept_left = x + crop.Left * per_x
        kept_top = y + crop.Top * per_y
        kept_right = x + width - crop.Right * per_x
        kept_bottom = y + height - crop.Bottom * per_y

        left, top = max(kept_left, 0), max(kept_top, 0)
        right, bottom = min(kept_right, PANE[0]), min(kept_bottom, PANE[1])

        assert (left, top, right - left, bottom - top) == _approx(shown.target)

    def test_there_is_none_too_big_to_draw(self):
        # 16000x9000: a side it could have, more pixels than it could
        assert calc_whole_placement(VIDEO, PANE, _view(scale=10.0)) is None
        assert calc_whole_placement(VIDEO, PANE, _view(scale=3.0)) is not None


class TestWholeGeometry:
    """What VLC is told for a picture it turns: its shape, and no crop."""

    def test_the_shape_is_given_the_way_the_frame_is_stored(self):
        # on its side 360x640, covering 400x500 at 400x711, stored 711x400
        geometry = calc_whole_geometry((640, 360), (400, 500), _view(), is_turned=True)

        assert geometry == ("711:400", "+0+0+0+0")

    def test_a_picture_turned_over_keeps_its_shape(self):
        # upside down, 640x360 covers 400x500 at 889x500
        geometry = calc_whole_geometry((640, 360), (400, 500), _view())

        assert geometry == ("889:500", "+0+0+0+0")

    def test_stretched_it_takes_the_pane_s_shape(self):
        view = _view(VideoAspect.STRETCH)

        geometry = calc_whole_geometry((640, 360), (400, 500), view, is_turned=True)

        assert geometry == ("5:4", "+0+0+0+0")

    def test_with_a_crop_of_the_users_it_is_all_of_the_frame(self):
        # 640x350 kept covers 400x500 at 914x500, the whole frame 914x514
        view = _view(crop=VideoCrop(0, 0, 0, 10))

        geometry = calc_whole_geometry((640, 360), (400, 500), view)

        assert geometry == ("457:257", "+0+0+0+0")


class TestStep:
    """What a move right and a move down add to the shift."""

    def test_is_a_share_of_what_is_on_show(self):
        # 1080x1080 of it on show in a square pane
        _, down = calc_view_step(VIDEO, SQUARE, _view())

        assert down == 54

    def test_is_shorter_zoomed_in(self):
        assert calc_view_step(VIDEO, SQUARE, _view(scale=2.0)) == (-27, -27)

    def test_looks_further_that_way_where_the_picture_is_bigger(self):
        """Going right brings more of its right side in: it slides left."""

        across, _ = calc_view_step(VIDEO, SQUARE, _view())

        assert across == -54

    def test_moves_the_picture_that_way_where_it_is_smaller(self):
        # all 1920x1080 on show, letterboxed, with room up and down
        assert calc_view_step(VIDEO, SQUARE, _view(VideoAspect.NONE)) == (96, 54)

    def test_takes_each_way_on_its_own(self):
        # zoomed out of a tall pane: bigger across, smaller down
        view = _view(VideoAspect.NONE, scale=1.5)

        across, down = calc_view_step(VIDEO, (900, 2000), view)

        assert across < 0 < down

    def test_is_the_same_past_the_edges(self):
        """Less of it is on show out there, but a press goes as far."""

        view = _view(VideoAspect.NONE, is_shift_past_edges=True)
        moved_out = view._replace(shift=VideoShift(0, -900))

        assert calc_view_step(VIDEO, SQUARE, moved_out) == calc_view_step(
            VIDEO, SQUARE, view
        )

    def test_is_at_least_a_pixel(self):
        assert calc_view_step((10, 10), SQUARE, _view(scale=10.0)) == (-1, -1)

    def test_is_nothing_with_nothing_to_work_from(self):
        assert calc_view_step((0, 0), SQUARE, _view()) == (0, 0)


class TestMovedShift:
    """Where so many moves take the picture: whole steps from the anchor."""

    def test_goes_a_whole_step_at_a_time(self):
        # zoomed in, 540x540 on show and 27 a step, looking right and up
        view = _view(scale=2.0)

        assert calc_moved_shift(VIDEO, SQUARE, view, (2, -1)) == VideoShift(-54, 27)

    def test_from_between_steps_goes_to_the_next(self):
        view = _view(VideoAspect.NONE, shift=VideoShift(0, -70))

        assert calc_moved_shift(VIDEO, SQUARE, view, (0, 1)) == VideoShift(0, -54)
        assert calc_moved_shift(VIDEO, SQUARE, view, (0, -1)) == VideoShift(0, -108)

    def test_is_held_where_the_picture_stops(self):
        view = _view(VideoAspect.NONE, shift=VideoShift(0, 400))

        assert calc_moved_shift(VIDEO, SQUARE, view, (0, 3)) == VideoShift(0, 420)

    def test_stays_put_with_nothing_to_work_from(self):
        view = _view(shift=VideoShift(7, 7))

        assert calc_moved_shift((0, 0), SQUARE, view, (1, 1)) == VideoShift(7, 7)


class TestPlacementNothing:
    @pytest.mark.parametrize(
        ("frame", "pane"),
        [((0, 0), PANE), (VIDEO, (0, 900)), (VIDEO, (1600, 0))],
    )
    def test_no_size_is_no_placement(self, frame, pane):
        assert calc_view_placement(frame, pane, _view()) is None


class TestViewGeometry:
    """What VLC is told: crop to the part on show, give it the pane's shape."""

    @pytest.mark.parametrize("aspect", list(VideoAspect))
    def test_same_shape_keeps_it_all(self, aspect):
        assert calc_view_geometry(VIDEO, PANE, _view(aspect)) == ("16:9", "+0+0+0+0")

    def test_fit_crops_a_square_from_the_middle(self):
        assert calc_view_geometry(VIDEO, SQUARE, _view()) == ("16:9", "+420+0+420+0")

    def test_none_letterboxes_user_region(self):
        crop = VideoCrop(100, 50, 40, 30)

        override, geometry = calc_view_geometry(
            VIDEO, PANE, _view(VideoAspect.NONE, crop=crop)
        )

        assert geometry == "+100+50+40+30"
        # shown in its own shape, 1780x1000
        assert _shown_ratio(override, VIDEO, crop) == pytest.approx(1.78, abs=1e-3)

    def test_fit_extends_borders_when_region_taller_than_pane(self):
        # Region 960x1080 (8:9) in a 16:9 pane -> crop 270 top/bottom.
        crop = VideoCrop(480, 0, 480, 0)

        assert calc_view_geometry(VIDEO, PANE, _view(crop=crop)) == (
            "16:9",
            "+480+270+480+270",
        )

    def test_fit_extends_borders_when_region_wider_than_pane(self):
        # Region 1920x540 (32:9) in a 16:9 pane -> crop 480 left/right.
        crop = VideoCrop(0, 270, 0, 270)

        assert calc_view_geometry(VIDEO, PANE, _view(crop=crop)) == (
            "16:9",
            "+480+270+480+270",
        )

    def test_fit_borders_round_to_nearest_pixel(self):
        # Region 959x1080 -> target height 539.4375 -> extra rounds to 270.
        crop = VideoCrop(481, 0, 480, 0)

        _, geometry = calc_view_geometry(VIDEO, PANE, _view(crop=crop))

        assert geometry == "+481+270+480+270"

    def test_fit_leaves_matching_region_unchanged(self):
        # Region 1600x900 already matches the 16:9 pane; no extra borders.
        crop = VideoCrop(160, 90, 160, 90)

        assert calc_view_geometry(VIDEO, PANE, _view(crop=crop)) == (
            "16:9",
            "+160+90+160+90",
        )

    def test_fit_does_not_zero_out_tiny_region(self):
        # 4x1 region in a 1x10000 pane: rounding must leave a pixel each way.
        crop = VideoCrop(958, 1079, 958, 0)

        _, geometry = calc_view_geometry(VIDEO, (1, 10000), _view(crop=crop))
        borders = _borders(geometry)

        assert calc_crop_region(VIDEO, borders)[2:] == (1, 1)

    def test_zoom_is_in_the_crop(self):
        assert calc_view_geometry(VIDEO, PANE, _view(scale=2.0)) == (
            "16:9",
            "+480+270+480+270",
        )

    def test_stretch_compensates_override_for_cropped_region(self):
        # Region 960x1080 must display as 16:9; VLC derives the SAR from the
        # pre-crop dims, so the override is compensated to 32:9.
        crop = VideoCrop(480, 0, 480, 0)

        assert calc_view_geometry(
            VIDEO, PANE, _view(VideoAspect.STRETCH, crop=crop)
        ) == (
            "32:9",
            "+480+0+480+0",
        )

    def test_stretch_compensates_vertical_crop(self):
        # Region 1920x540 must display as 16:9 -> override 8:9.
        crop = VideoCrop(0, 270, 0, 270)

        assert calc_view_geometry(
            VIDEO, PANE, _view(VideoAspect.STRETCH, crop=crop)
        ) == (
            "8:9",
            "+0+270+0+270",
        )

    def test_stretch_too_thin_for_vlc_falls_back_to_native(self):
        # 1x1 region in a 1px-wide huge pane: no SAR VLC can do its sums on
        # comes near, so "0:0" leaves the picture its own shape
        crop = VideoCrop(1919, 1079, 0, 0)

        assert calc_view_geometry(
            VIDEO, (1, 600000), _view(VideoAspect.STRETCH, crop=crop)
        ) == ("0:0", "+1919+1079+0+0")

    def test_stretch_degenerate_override_falls_back_to_native(self):
        # 1x1 region in a 1px-tall huge pane -> absurd ratio -> "0:0" resets
        # the override in VLC (letterbox) instead of overflowing its SAR math.
        crop = VideoCrop(1919, 1079, 0, 0)

        assert calc_view_geometry(
            VIDEO, (600000, 1), _view(VideoAspect.STRETCH, crop=crop)
        ) == ("0:0", "+1919+1079+0+0")

    def test_zero_pane_size_falls_back_to_letterbox(self):
        crop = VideoCrop(10, 10, 10, 10)

        assert calc_view_geometry(VIDEO, (0, 900), _view(crop=crop)) == (
            "1920:1080",
            "+10+10+10+10",
        )

    def test_zero_pane_size_falls_back_to_the_turned_shape(self):
        assert calc_view_geometry(
            VIDEO, (0, 900), _view(), VideoTransform.ROTATE_90
        ) == ("1080:1920", "+0+0+0+0")

    def test_zero_video_size_falls_back_to_letterbox(self):
        crop = VideoCrop(10, 10, 10, 10)

        assert calc_view_geometry((0, 0), PANE, _view(crop=crop)) == (
            "0:0",
            "+10+10+10+10",
        )

    @pytest.mark.parametrize(
        ("pane", "crop"),
        [
            ((1600, 899), VideoCrop(100, 50, 40, 30)),
            ((1597, 900), VideoCrop(7, 0, 3, 0)),
            ((901, 1777), VideoCrop(1, 3, 0, 2)),
        ],
    )
    def test_override_fits_vlc_sar_range_without_giving_up(self, pane, crop):
        """A ratio that won't reduce is approximated, not reset to native."""

        for aspect in VideoAspect:
            view = _view(aspect, crop=crop)
            override, geometry = calc_view_geometry(VIDEO, pane, view)
            num, den = (int(part) for part in override.split(":"))
            _, _, target_w, target_h = calc_view_placement(VIDEO, pane, view).target

            assert 0 < num
            assert 0 < den
            assert _fits_vlc(override, VIDEO, _borders(geometry))
            assert _shown_ratio(override, VIDEO, _borders(geometry)) == pytest.approx(
                round(target_w) / round(target_h), rel=1e-4
            )

    def test_moved_past_an_edge_it_is_not_placed_out_of_shape(self):
        """A crop that leaves an awkward region made VLC's sums on the
        SAR wrap round, and it placed the picture 1527 high in 675."""

        view = _view(shift=VideoShift(0, -41), is_shift_past_edges=True)

        override, geometry = calc_view_geometry(VIDEO, (1039, 684), view)

        assert geometry == "+140+41+140+0"
        assert _fits_vlc(override, VIDEO, _borders(geometry))

    def test_every_override_fits_vlc_s_sums(self):
        rng = random.Random(7)

        for _ in range(3000):
            frame = rng.choice([VIDEO, (1917, 1079), (720, 576), (4096, 2160)])
            pane = (rng.randint(50, 2000), rng.randint(50, 1200))
            view = _view(
                rng.choice(list(VideoAspect)),
                rng.choice([1.0, 1.3, 2.0, 7.5]),
                VideoCrop(*(rng.choice([0, 0, 3, 41]) for _ in range(4))),
                rng.choice(list(VideoAnchor)),
                VideoShift(rng.randint(-3000, 3000), rng.randint(-3000, 3000)),
                rng.random() < 0.5,
            )
            override, geometry = calc_view_geometry(frame, pane, view)
            _, _, target_w, target_h = calc_view_placement(frame, pane, view).target

            assert _fits_vlc(override, frame, _borders(geometry))
            # a frame whose sides share nothing leaves the SAR's terms in
            # the hundreds: within a pixel in five hundred
            assert _shown_ratio(override, frame, _borders(geometry)) == pytest.approx(
                round(target_w) / round(target_h), rel=2e-3
            )

    @pytest.mark.parametrize(
        ("anchor", "geometry"),
        [
            (VideoAnchor.LEFT, "+0+0+840+0"),
            (VideoAnchor.CENTER, "+420+0+420+0"),
            (VideoAnchor.BOTTOM_RIGHT, "+840+0+0+0"),
        ],
    )
    def test_the_anchor_is_in_the_crop(self, anchor, geometry):
        assert calc_view_geometry(VIDEO, SQUARE, _view(anchor=anchor)) == (
            "16:9",
            geometry,
        )

    def test_the_shift_is_in_the_crop(self):
        view = _view(scale=2.0, shift=VideoShift(-200, 100))

        assert calc_view_geometry(VIDEO, PANE, view) == ("16:9", "+680+170+280+370")


class TestViewGeometryRotated:
    """The crop is in the unrotated frame; the override shapes it back."""

    FRAME = (640, 360)

    def test_fit_covers_a_wide_pane(self):
        override, geometry = calc_view_geometry(
            self.FRAME, (640, 360), _view(), VideoTransform.ROTATE_90
        )

        borders = _borders(geometry)
        assert borders == VideoCrop(0, 123, 0, 123)
        assert _shown_ratio(override, self.FRAME, borders) == pytest.approx(
            640 / 360, rel=0.01
        )

    def test_none_with_a_crop_keeps_the_turned_shape(self):
        crop = VideoCrop(160, 0, 0, 0)

        override, geometry = calc_view_geometry(
            self.FRAME,
            (360, 640),
            _view(VideoAspect.NONE, crop=crop),
            VideoTransform.ROTATE_90,
        )

        assert geometry == "+160+0+0+0"
        # 480 frame pixels across are 270 on screen, 360 down are 640
        assert _shown_ratio(override, self.FRAME, crop) == pytest.approx(270 / 640)


class TestViewBorders:
    def test_is_what_vlc_is_told_to_crop(self):
        crop = VideoCrop(10, 20, 30, 40)

        for aspect in VideoAspect:
            for scale in (1.0, 2.5):
                view = _view(aspect, scale, crop)
                borders = calc_view_borders((800, 600), (500, 200), view)
                _, geometry = calc_view_geometry((800, 600), (500, 200), view)

                assert _borders(geometry) == borders

    def test_nothing_to_work_from_is_the_user_crop(self):
        crop = VideoCrop(10, 20, 30, 40)

        assert calc_view_borders((0, 0), PANE, _view(crop=crop)) == crop


class TestCropRegion:
    @pytest.mark.parametrize(
        ("crop", "expected"),
        [
            (VideoCrop(480, 0, 480, 0), (480, 0, 960, 1080)),
            (VideoCrop(2000, 0, 0, 0), (1919, 0, 1, 1080)),
            (VideoCrop(0, 0, 3000, 3000), (0, 0, 1, 1)),
            (VideoCrop(2000, 2000, 2000, 2000), (1919, 1079, 1, 1)),
        ],
    )
    def test_clamped_to_video_bounds(self, crop, expected):
        assert calc_crop_region(VIDEO, crop) == expected
