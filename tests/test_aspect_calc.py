import math

import pytest

from gridplayer.params.static import (
    NO_FILL_LIMIT,
    VideoAnchor,
    VideoCellViewMode,
    VideoCrop,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.utils.aspect_calc import (
    calc_crop_region,
    calc_dragged_shift,
    calc_followed_view,
    calc_moved_shift,
    calc_picture_rect,
    calc_picture_shape,
    calc_ratio_crop,
    calc_selection_zoom,
    calc_shared_view,
    calc_shift_range,
    calc_shown_pixel_aspect,
    calc_view_borders,
    calc_view_placement,
    calc_view_shift,
    calc_view_step,
    calc_whole_placement,
    calc_zoomed_shift,
    parse_aspect_ratio,
)

VIDEO = (1920, 1080)
PANE = (1600, 900)
SQUARE = (900, 900)
NO_CROP = VideoCrop(0, 0, 0, 0)
NO_SHIFT = VideoShift(0, 0)


def _view(
    cell_view_mode=VideoCellViewMode.FILL,
    scale=1.0,
    crop=NO_CROP,
    anchor=VideoAnchor.CENTER,
    shift=NO_SHIFT,
    is_shift_past_edges=False,
):
    return ViewParams(cell_view_mode, scale, crop, anchor, shift, is_shift_past_edges)


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
            VIDEO, SQUARE, _view(VideoCellViewMode.FIT, scale=2.0)
        )

        assert placement.target == _approx((0, 0, 900, 900))
        assert placement.source == _approx((480, 60, 960, 960))

    def test_none_keeps_letterbox_while_it_fits(self):
        placement = calc_view_placement(
            VIDEO, (900, 2000), _view(VideoCellViewMode.FIT, scale=1.5)
        )

        # 900x506.25 fitted, 1350x759.375 zoomed
        assert placement.target == _approx((0, (2000 - 759.375) / 2, 900, 759.375))
        assert placement.source == _approx((320, 0, 1280, 1080))


class TestPlacementNoneAndStretch:
    def test_none_letterboxes_in_the_middle(self):
        placement = calc_view_placement(VIDEO, SQUARE, _view(VideoCellViewMode.FIT))

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
            VIDEO, SQUARE, _view(VideoCellViewMode.FIT, anchor=anchor)
        )

        assert placement.target == _approx((0, top, 900, 506.25))

    def test_none_is_kept_whole_inside_the_pane(self):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(VideoCellViewMode.FIT, shift=VideoShift(0, -2000))
        )

        assert placement.target == _approx((0, 0, 900, 506.25))

    @pytest.mark.parametrize("anchor", list(VideoAnchor))
    def test_stretch_has_no_room_to_move(self, anchor):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(VideoCellViewMode.STRETCH, anchor=anchor)
        )

        assert placement.source == _approx((0, 0, 1920, 1080))
        assert placement.target == _approx((0, 0, 900, 900))

    def test_stretch_zoomed_can_pan(self):
        placement = calc_view_placement(
            VIDEO,
            SQUARE,
            _view(VideoCellViewMode.STRETCH, scale=2.0, anchor=VideoAnchor.TOP),
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
            self.FRAME,
            (640, 360),
            _view(VideoCellViewMode.FIT),
            VideoTransform.ROTATE_270,
        )

        # 360 tall, so 202.5 wide
        assert placement.target == _approx(((640 - 202.5) / 2, 0, 202.5, 360))

    def test_a_crop_takes_from_the_side_it_is_named_for(self):
        # Left 160 of the 640 frame pixels across is a quarter of the width
        # on screen, whichever way the picture was turned
        placement = calc_view_placement(
            self.FRAME,
            (360, 640),
            _view(VideoCellViewMode.FIT, crop=VideoCrop(160, 0, 0, 0)),
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
        view = _view(VideoCellViewMode.FIT, shift=VideoShift(10, 1000))

        assert calc_view_shift(VIDEO, SQUARE, view) == VideoShift(0, 420)

    def test_nothing_to_work_from_leaves_it_as_it_is(self):
        view = _view(shift=VideoShift(5000, 0))

        assert calc_view_shift((0, 0), SQUARE, view) == VideoShift(5000, 0)


class TestDraggedShift:
    """Where the picture goes, dragged along with the pointer."""

    def test_it_goes_as_far_as_the_pointer(self):
        # 1600x900 in the square, 900/1080 pane pixels a frame pixel
        shift, left_over = calc_dragged_shift(VIDEO, SQUARE, _view(), (50, 0))

        assert shift == VideoShift(60, 0)
        assert left_over == _approx((0, 0))

    def test_a_bigger_picture_goes_the_pointer_s_way_too(self):
        """Not the way a move from the menu takes it: that is looking
        further, and this is taking hold of the picture."""

        shift, _ = calc_dragged_shift(VIDEO, SQUARE, _view(), (-50, 0))

        assert shift == VideoShift(-60, 0)

    def test_it_goes_from_where_the_picture_stands(self):
        view = _view(shift=VideoShift(5000, 0))

        shift, _ = calc_dragged_shift(VIDEO, SQUARE, view, (-50, 0))

        assert shift == VideoShift(360, 0)

    def test_less_than_a_frame_pixel_is_left_over_for_the_next_move(self):
        # zoomed in 4x, 10/3 pane pixels a frame pixel
        view = _view(scale=4.0)

        shift, left_over = calc_dragged_shift(VIDEO, SQUARE, view, (1, 0))

        assert shift == NO_SHIFT
        assert left_over == _approx((1, 0))

        shift, left_over = calc_dragged_shift(VIDEO, SQUARE, view, (2, 0))

        assert shift == VideoShift(1, 0)
        assert left_over == _approx((2 - 10 / 3, 0))

    def test_held_at_an_edge_nothing_is_left_over(self):
        shift, left_over = calc_dragged_shift(VIDEO, SQUARE, _view(), (5000, 1.4))

        assert shift == VideoShift(420, 0)
        assert left_over == _approx((0, 0))

    def test_past_the_edges_it_goes_further(self):
        view = _view(is_shift_past_edges=True)

        shift, _ = calc_dragged_shift(VIDEO, SQUARE, view, (5000, 0))

        assert shift == calc_shift_range(VIDEO, SQUARE, view)[1]._replace(Y=0)
        assert shift.X > 420

    def test_nothing_to_work_from_leaves_it_as_it_is(self):
        view = _view(shift=VideoShift(10, 0))

        assert calc_dragged_shift((0, 0), SQUARE, view, (50, 0)) == (
            VideoShift(10, 0),
            (0.0, 0.0),
        )


def _under(view, focus, frame=VIDEO, pane=SQUARE, transform=VideoTransform.NONE):
    """The frame point under a pane point, from what the crop keeps."""

    left, top, width, height = calc_picture_rect(frame, pane, view, transform)
    _, _, region_w, region_h = calc_crop_region(frame, view.crop)

    return (
        (focus[0] - left) * region_w / width,
        (focus[1] - top) * region_h / height,
    )


class TestZoomedShift:
    """A zoom about a point: what is under it stays under it."""

    def test_it_keeps_the_point_under_the_focus(self):
        # 1600x900 at 900/1080, (1140, 360) under (600, 300); at 2x that
        # takes the picture to (-1300, -300), 150 pane pixels from the
        # middle each way, 90 frame pixels at 1800/1080
        shift, kept = calc_zoomed_shift(VIDEO, SQUARE, _view(), 2.0, (600, 300))

        assert shift == VideoShift(-90, 90)
        assert kept == _approx((1140, 360))

    def test_about_the_anchor_s_place_it_is_the_usual_zoom(self):
        shift, _ = calc_zoomed_shift(VIDEO, SQUARE, _view(), 2.0, (450, 450))

        assert shift == NO_SHIFT

    @pytest.mark.parametrize(
        ("view", "transform"),
        [
            (_view(), VideoTransform.NONE),
            (_view(anchor=VideoAnchor.TOP_LEFT), VideoTransform.NONE),
            (_view(anchor=VideoAnchor.BOTTOM_RIGHT), VideoTransform.NONE),
            (_view(shift=VideoShift(-200, 0)), VideoTransform.NONE),
            (_view(crop=VideoCrop(100, 40, 300, 0)), VideoTransform.NONE),
            (_view(cell_view_mode=VideoCellViewMode.STRETCH), VideoTransform.NONE),
            (_view(scale=1.5, is_shift_past_edges=True), VideoTransform.NONE),
            (_view(), VideoTransform.ROTATE_90),
        ],
    )
    @pytest.mark.parametrize("scale", [1.1, 2.0, 3.7])
    def test_wherever_the_picture_is_and_however_it_is_shown(
        self, view, transform, scale
    ):
        focus = (530, 410)
        point = _under(view, focus, transform=transform)

        shift, kept = calc_zoomed_shift(VIDEO, SQUARE, view, scale, focus, transform)
        zoomed = view._replace(scale=scale, shift=shift)

        assert kept == _approx(point)
        # off by what the whole frame pixels the shift is in round away
        assert _under(zoomed, focus, transform=transform) == pytest.approx(
            point, abs=0.5
        )

    def test_near_an_edge_the_point_slides_off_rather_than_black_coming_in(self):
        view = _view(scale=2.0)
        _, highest = calc_shift_range(VIDEO, SQUARE, view)
        view = view._replace(shift=highest)

        # the left edge in the pane's: zoomed out about a point beside it,
        # it would come away from the edge
        shift, kept = calc_zoomed_shift(VIDEO, SQUARE, view, 1.5, (5, 450))

        zoomed = view._replace(scale=1.5)
        assert shift.X == calc_shift_range(VIDEO, SQUARE, zoomed)[1].X
        assert kept[0] is None

    def test_an_axis_the_picture_fits_on_goes_to_the_anchor_s_place(self):
        """Letterboxed, 900x506.25, and still only 759.375 tall at 1.5x."""

        view = _view(cell_view_mode=VideoCellViewMode.FIT, shift=VideoShift(0, 100))

        shift, kept = calc_zoomed_shift(VIDEO, SQUARE, view, 1.5, (300, 300))

        assert shift.Y == 0
        assert kept[1] is None
        # across it is bigger than the pane, and follows the focus
        assert shift.X != 0
        assert kept[0] is not None

    def test_past_the_edges_it_follows_the_focus_on_that_axis_too(self):
        view = _view(cell_view_mode=VideoCellViewMode.FIT, is_shift_past_edges=True)
        point = _under(view, (300, 300))

        shift, kept = calc_zoomed_shift(VIDEO, SQUARE, view, 1.5, (300, 300))

        assert shift.Y != 0
        assert kept == _approx(point)

    def test_over_the_bars_the_nearest_part_of_the_picture_stays(self):
        """The picture's top row, at 196.875 in the pane, stays there: at
        1.5x, 70.3125 from the top centred, 180 frame pixels further down
        at 0.703125 pane pixels each. Not kept, the edge being no focus."""

        view = _view(cell_view_mode=VideoCellViewMode.FIT, is_shift_past_edges=True)

        shift, kept = calc_zoomed_shift(VIDEO, SQUARE, view, 1.5, (450, 50))

        assert shift.Y == 180
        assert kept[1] is None
        assert kept[0] is not None

    def test_zoomed_in_and_back_out_about_a_point_it_is_where_it_was(self):
        scales = [round(1 + step / 10, 1) for step in range(1, 21)]
        view, kept = _view(), (None, None)

        for scale in [*scales, *reversed(scales[:-1]), 1.0]:
            shift, kept = calc_zoomed_shift(
                VIDEO, SQUARE, view, scale, (600, 300), kept=kept
            )
            view = view._replace(scale=scale, shift=shift)

        assert view.shift == NO_SHIFT

    def test_the_kept_point_does_not_wander_far_zoomed_in(self):
        """640x360 in a 1600x900 pane at 10x is 25 screen pixels a frame
        pixel: zoomed about the point found under the focus each time, it
        could wander by half of one a notch."""

        small, pane, focus = (640, 360), (1600, 900), (1003, 517)
        view, kept = _view(), (None, None)
        point = _under(view, focus, small, pane)

        for step in range(1, 91):
            scale = round(1 + step / 10, 1)
            shift, kept = calc_zoomed_shift(small, pane, view, scale, focus, kept=kept)
            view = view._replace(scale=scale, shift=shift)

            assert _under(view, focus, small, pane) == pytest.approx(point, abs=0.5)

    def test_nothing_to_work_from_leaves_it_as_it_is(self):
        view = _view(shift=VideoShift(10, 0))

        assert calc_zoomed_shift((0, 0), SQUARE, view, 2.0, (5, 5)) == (
            VideoShift(10, 0),
            (None, None),
        )


def _at(view, point, frame=VIDEO, pane=SQUARE, transform=VideoTransform.NONE):
    """The pane point over a frame point, the other way round from _under."""

    left, top, width, height = calc_picture_rect(frame, pane, view, transform)
    _, _, region_w, region_h = calc_crop_region(frame, view.crop)

    return (
        left + point[0] * width / region_w,
        top + point[1] * height / region_h,
    )


class TestSelectionZoom:
    """A part of the picture fitted into the pane, in its middle."""

    def test_it_fits_the_selection_into_the_pane_in_its_middle(self):
        # 1600x900 at 900/1080, from -350 across: the selection's middle,
        # (250, 250), is over (720, 300); at 3x, 2.5 pane pixels a frame
        # pixel, the picture goes to (-1350, -300) to have it at (450, 450),
        # 600 right and down of where it would be centred
        scale, shift = calc_selection_zoom(VIDEO, SQUARE, _view(), (100, 100, 300, 300))

        assert scale == 3.0
        assert shift == VideoShift(240, 240)

    @pytest.mark.parametrize(
        ("view", "transform"),
        [
            (_view(), VideoTransform.NONE),
            (_view(anchor=VideoAnchor.TOP_LEFT), VideoTransform.NONE),
            (_view(anchor=VideoAnchor.BOTTOM_RIGHT), VideoTransform.NONE),
            (_view(shift=VideoShift(-200, 0)), VideoTransform.NONE),
            (_view(crop=VideoCrop(100, 40, 300, 0)), VideoTransform.NONE),
            (_view(cell_view_mode=VideoCellViewMode.STRETCH), VideoTransform.NONE),
            (_view(scale=1.5, shift=VideoShift(90, -60)), VideoTransform.NONE),
            (_view(scale=1.5, is_shift_past_edges=True), VideoTransform.NONE),
            (_view(), VideoTransform.ROTATE_90),
        ],
    )
    @pytest.mark.parametrize(
        "selection",
        [(300, 250, 200, 150), (420, 380, 60, 140), (250, 300, 400, 120)],
    )
    def test_wherever_the_picture_is_and_however_it_is_shown(
        self, view, transform, selection
    ):
        x, y, width, height = selection
        middle = _under(view, (x + width / 2, y + height / 2), transform=transform)
        corners = (
            _under(view, (x, y), transform=transform),
            _under(view, (x + width, y + height), transform=transform),
        )

        scale, shift = calc_selection_zoom(VIDEO, SQUARE, view, selection, transform)
        zoomed = view._replace(scale=scale, shift=shift)

        # off by what the whole frame pixels the shift is in round away
        assert _under(zoomed, (450, 450), transform=transform) == pytest.approx(
            middle, abs=0.5
        )

        (left, top), (right, bottom) = (
            _at(zoomed, corner, transform=transform) for corner in corners
        )
        assert right - left <= 900 + 1e-6
        assert bottom - top <= 900 + 1e-6
        # as big as it goes, in hundredths
        assert max(right - left, bottom - top) > 900 * (1 - 0.01 / scale) - 1e-6

    def test_it_fits_rather_than_fills(self):
        """600x100: as wide as the pane, and the rest of the picture above
        and below it, rather than 100 as tall as the pane and cut off."""

        scale, _ = calc_selection_zoom(VIDEO, SQUARE, _view(), (150, 400, 600, 100))

        assert scale == 1.5

    def test_the_scale_is_in_hundredths_down(self):
        """900/350 is 2.5714..., which would not read as a number."""

        scale, _ = calc_selection_zoom(VIDEO, SQUARE, _view(), (275, 275, 350, 350))

        assert scale == 2.57

    def test_no_further_than_the_zoom_goes(self):
        scale, shift = calc_selection_zoom(
            VIDEO, SQUARE, _view(), (595, 395, 10, 10), max_scale=10.0
        )
        zoomed = _view(scale=scale, shift=shift)

        assert scale == 10.0
        # still in the middle, smaller than the pane
        assert _under(zoomed, (450, 450)) == pytest.approx(
            _under(_view(), (600, 400)), abs=0.5
        )

    def test_it_never_zooms_out(self):
        """All of what is on show selected, a zoom in already."""

        view = _view(scale=2.0, shift=VideoShift(100, 0))

        scale, shift = calc_selection_zoom(VIDEO, SQUARE, view, (0, 0, 900, 900))

        assert scale == 2.0
        assert shift == VideoShift(100, 0)

    def test_by_an_edge_it_goes_off_the_middle_rather_than_black_coming_in(self):
        """Against the top of the picture; across, it is cut off by the pane
        either side, and the selection's middle can go to the pane's."""

        view = _view()

        scale, shift = calc_selection_zoom(VIDEO, SQUARE, view, (400, 0, 100, 100))
        zoomed = view._replace(scale=scale, shift=shift)

        assert scale == 9.0
        assert shift.Y == calc_shift_range(VIDEO, SQUARE, zoomed)[1].Y
        # the pane's top row is the selection's still
        assert _under(zoomed, (450, 0))[1] == pytest.approx(_under(view, (450, 0))[1])
        assert _under(zoomed, (450, 450))[0] == pytest.approx(
            _under(view, (450, 50))[0], abs=0.5
        )

    def test_only_what_is_over_the_picture_counts(self):
        """Letterboxed, 900x506.25 from 196.875 down: 450x103.125 of it."""

        view = _view(cell_view_mode=VideoCellViewMode.FIT)

        scale, _ = calc_selection_zoom(VIDEO, SQUARE, view, (0, 0, 450, 300))

        assert scale == 2.0

    def test_over_the_bars_alone_there_is_nothing_to_zoom_to(self):
        view = _view(cell_view_mode=VideoCellViewMode.FIT)

        assert calc_selection_zoom(VIDEO, SQUARE, view, (0, 0, 900, 150)) is None

    def test_an_axis_the_picture_fits_on_goes_to_the_anchor_s_place(self):
        """Letterboxed, and still only 759.375 tall at 1.5x."""

        view = _view(cell_view_mode=VideoCellViewMode.FIT)

        scale, shift = calc_selection_zoom(VIDEO, SQUARE, view, (0, 300, 600, 100))

        assert scale == 1.5
        assert shift.Y == 0
        # across it is bigger than the pane, and goes against the left side
        zoomed = view._replace(scale=1.5)
        assert shift.X == calc_shift_range(VIDEO, SQUARE, zoomed)[1].X

    def test_past_the_edges_it_is_in_the_middle_on_that_axis_too(self):
        view = _view(cell_view_mode=VideoCellViewMode.FIT, is_shift_past_edges=True)
        middle = _under(view, (300, 350))

        scale, shift = calc_selection_zoom(VIDEO, SQUARE, view, (0, 300, 600, 100))
        zoomed = view._replace(scale=scale, shift=shift)

        assert _under(zoomed, (450, 450)) == pytest.approx(middle, abs=0.5)

    def test_nothing_to_work_from_is_nothing_to_zoom_to(self):
        assert calc_selection_zoom((0, 0), SQUARE, _view(), (5, 5, 50, 50)) is None


def _middle(view, frame, pane=PANE):
    """The share of the picture at the pane's middle, across and down."""

    left, top, width, height = calc_picture_rect(frame, pane, view)

    return (pane[0] / 2 - left) / width, (pane[1] / 2 - top) / height


def _followed(leader, follower=None, frame=VIDEO, pane=PANE):
    shared = calc_shared_view(VIDEO, PANE, leader)

    return calc_followed_view(frame, pane, follower or _view(), shared)


class TestFollowingAView:
    """Another video showing the part of its picture one shows of its own."""

    def test_the_same_video_in_the_same_pane_is_the_same_pixel_for_pixel(self):
        leader = _view(scale=3.3, anchor=VideoAnchor.TOP, shift=VideoShift(-317, -123))

        followed = _followed(leader, _view(scale=7.0, shift=VideoShift(500, 0)))

        assert followed == leader

    def test_one_held_by_its_edges_is_followed_where_it_stands(self):
        leader = _view(scale=2.0, shift=VideoShift(5000, 0))

        followed = _followed(leader)

        assert followed.shift == calc_view_shift(VIDEO, PANE, leader)

    def test_a_smaller_copy_shows_the_same_part(self):
        leader = _view(scale=3.0, shift=VideoShift(-300, 120))

        followed = _followed(leader, frame=(960, 540))

        assert followed.shift == VideoShift(-150, 60)
        assert _middle(followed, (960, 540)) == pytest.approx(_middle(leader, VIDEO))

    def test_a_pane_of_another_size_shows_the_same_part(self):
        leader = _view(scale=3.0, shift=VideoShift(-300, 120))

        followed = _followed(leader, pane=(1601, 900))

        # as near as a whole frame pixel gets
        assert _middle(followed, VIDEO, (1601, 900)) == pytest.approx(
            _middle(leader, VIDEO), abs=0.5 / 1080
        )

    def test_a_picture_of_another_shape_has_the_same_point_in_the_middle(self):
        leader = _view(scale=3.0, shift=VideoShift(-300, 120))

        followed = _followed(
            leader, _view(cell_view_mode=VideoCellViewMode.FIT), frame=(640, 480)
        )

        assert followed.cell_view_mode == VideoCellViewMode.FIT
        assert _middle(followed, (640, 480)) == pytest.approx(
            _middle(leader, VIDEO), abs=0.5 / 480
        )

    def test_a_picture_smaller_than_its_pane_stands_where_the_other_does(self):
        # 1200x900 in 1600x900 and 2000x900, moved a quarter of the way
        # across the room beside it, 100 of 400
        leader = _view(cell_view_mode=VideoCellViewMode.FIT, shift=VideoShift(-120, 0))
        assert calc_picture_rect((1440, 1080), PANE, leader)[0] == pytest.approx(100)

        shared = calc_shared_view((1440, 1080), PANE, leader)
        followed = calc_followed_view(
            (1440, 1080),
            (2000, 900),
            _view(cell_view_mode=VideoCellViewMode.FIT),
            shared,
        )

        left = calc_picture_rect((1440, 1080), (2000, 900), followed)[0]

        assert left == pytest.approx(200, abs=900 / 1080)

    def test_one_against_a_corner_is_followed_into_it(self):
        leader = _view(
            cell_view_mode=VideoCellViewMode.FIT, anchor=VideoAnchor.TOP_LEFT
        )
        shared = calc_shared_view((1440, 1080), PANE, leader)

        followed = calc_followed_view(
            (1080, 1080), PANE, _view(cell_view_mode=VideoCellViewMode.FIT), shared
        )

        assert followed.anchor == VideoAnchor.TOP_LEFT
        assert followed.shift == NO_SHIFT
        assert calc_picture_rect((1080, 1080), PANE, followed)[:2] == (0, 0)

    def test_back_in_its_place_the_other_is_too(self):
        followed = _followed(
            _view(),
            _view(scale=4.0, shift=VideoShift(-90, 40)),
            frame=(960, 720),
        )

        assert followed.scale == 1.0
        assert followed.shift == NO_SHIFT

    def test_the_zoom_and_the_alignment_are_taken_and_the_rest_kept(self):
        follower = _view(
            cell_view_mode=VideoCellViewMode.STRETCH,
            scale=5.0,
            crop=VideoCrop(10, 20, 30, 40),
            anchor=VideoAnchor.TOP,
            is_shift_past_edges=True,
        )

        followed = _followed(
            _view(scale=2.0, anchor=VideoAnchor.BOTTOM_RIGHT), follower
        )

        assert followed.scale == 2.0
        assert followed.anchor == VideoAnchor.BOTTOM_RIGHT
        assert followed.cell_view_mode == VideoCellViewMode.STRETCH
        assert followed.crop == VideoCrop(10, 20, 30, 40)
        assert followed.is_shift_past_edges

    def test_past_the_edges_it_is_held_by_its_own(self):
        leader = _view(scale=2.0, shift=VideoShift(800, 0), is_shift_past_edges=True)

        followed = _followed(leader)

        assert followed.shift == calc_view_shift(
            VIDEO, PANE, _view(scale=2.0, shift=VideoShift(800, 0))
        )
        assert followed.shift.X < 800

    def test_nothing_without_a_frame(self):
        assert calc_shared_view((0, 0), PANE, _view()) is None
        assert _followed(_view(), frame=(0, 0)) is None


class TestShiftRange:
    """How far the shift can go each way, which is where it is held."""

    def test_it_is_the_room_either_side_of_the_anchor(self):
        # 700 pane pixels of room across, 840 frame pixels, half each way
        assert calc_shift_range(VIDEO, SQUARE, _view()) == (
            VideoShift(-420, 0),
            VideoShift(420, 0),
        )

    def test_against_an_edge_it_only_goes_away_from_it(self):
        view = _view(anchor=VideoAnchor.LEFT)

        assert calc_shift_range(VIDEO, SQUARE, view) == (
            VideoShift(-840, 0),
            VideoShift(0, 0),
        )

    def test_past_the_edges_it_goes_as_far_as_half_on_show(self):
        # 900x506.25: half of 506.25 up or down past the 393.75 of room,
        # and half the pane across, 960 frame pixels every way
        view = _view(VideoCellViewMode.FIT, is_shift_past_edges=True)

        assert calc_shift_range(VIDEO, SQUARE, view) == (
            VideoShift(-960, -960),
            VideoShift(960, 960),
        )

    def test_nothing_to_work_from_leaves_it_as_it_is(self):
        view = _view(shift=VideoShift(5000, 0))

        assert calc_shift_range((0, 0), SQUARE, view) == (
            VideoShift(5000, 0),
            VideoShift(5000, 0),
        )


class TestPictureRect:
    """All of the picture where it goes, the pane's edges not cutting it."""

    def test_a_bigger_picture_reaches_past_the_pane(self):
        # 1600x900, 350 of it too wide each side
        assert calc_picture_rect(VIDEO, SQUARE, _view()) == _approx(
            (-350, 0, 1600, 900)
        )

    def test_it_is_what_the_crop_keeps_where_it_is_moved_to(self):
        # 960x1080 kept fits the square at 800x900, 50 in; 50 frame pixels
        # right is 41.7 more
        view = _view(
            VideoCellViewMode.FIT,
            crop=VideoCrop(480, 0, 480, 0),
            shift=VideoShift(50, 0),
        )

        assert calc_picture_rect(VIDEO, SQUARE, view) == _approx(
            (50 + 125 / 3, 0, 800, 900)
        )

    def test_there_is_none_with_nothing_to_place(self):
        assert calc_picture_rect((0, 0), SQUARE, _view()) is None


PHONE = (1080, 1920)


def _limited(fill_limit, **kwargs):
    return _view(**kwargs)._replace(fill_limit=fill_limit)


class TestFillLimit:
    """Fill, where it would cut more of the picture than the limit, shows
    it whole."""

    def test_no_limit_fills_whatever_it_cuts(self):
        # 1600x2844.4, 68% of it cut
        _, top, width, _ = calc_picture_rect(PHONE, PANE, _limited(NO_FILL_LIMIT))

        assert width == pytest.approx(1600)
        assert top == pytest.approx(-(1600 * 16 / 9 - 900) / 2)

    def test_one_cut_more_than_the_limit_is_shown_whole(self):
        assert calc_picture_rect(PHONE, PANE, _limited(30)) == _approx(
            ((1600 - 506.25) / 2, 0, 506.25, 900)
        )

    def test_one_cut_less_than_the_limit_fills(self):
        # 43.75% of 1600 cut to fill the square
        assert calc_picture_rect(VIDEO, SQUARE, _limited(50)) == _approx(
            (-350, 0, 1600, 900)
        )
        assert calc_picture_rect(VIDEO, SQUARE, _limited(40)) == _approx(
            (0, (900 - 506.25) / 2, 900, 506.25)
        )

    def test_none_allowed_shows_any_cut_whole(self):
        assert calc_picture_rect(VIDEO, SQUARE, _limited(0)) == _approx(
            (0, (900 - 506.25) / 2, 900, 506.25)
        )
        assert calc_picture_rect(VIDEO, PANE, _limited(0)) == _approx((0, 0, 1600, 900))

    def test_one_cut_by_the_limit_exactly_fills(self):
        # 4:3 filling 16:9 loses a quarter of it
        rect = calc_picture_rect((1440, 1080), PANE, _limited(25))

        assert rect == _approx((0, -150, 1600, 1200))

    def test_the_crop_is_what_it_goes_by(self):
        # the phone cut down to 1080x608 is about the pane's shape
        view = _limited(30, crop=VideoCrop(0, 656, 0, 656))

        assert calc_picture_rect(PHONE, PANE, view)[2] == pytest.approx(1600)

    def test_a_zoom_goes_on_top_of_the_whole_picture(self):
        assert calc_picture_rect(PHONE, PANE, _limited(30, scale=2.0)) == _approx(
            ((1600 - 1012.5) / 2, (900 - 1800) / 2, 1012.5, 1800)
        )

    def test_fit_and_stretch_are_left_alone(self):
        fit = _view(VideoCellViewMode.FIT)
        stretch = _view(VideoCellViewMode.STRETCH)

        for view in (fit, stretch):
            assert calc_picture_rect(
                PHONE, PANE, view._replace(fill_limit=10)
            ) == calc_picture_rect(PHONE, PANE, view)


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
            VideoCellViewMode.FIT, shift=VideoShift(0, -5000), is_shift_past_edges=True
        )

        placement = calc_view_placement(VIDEO, SQUARE, view)

        assert placement.target == _approx((0, 0, 900, 253.125))
        assert placement.source == _approx((0, 540, 1920, 540))

    @pytest.mark.parametrize(
        "view",
        [
            _view(shift=VideoShift(-300, 0)),
            _view(anchor=VideoAnchor.LEFT, shift=VideoShift(-500, 0)),
            _view(VideoCellViewMode.FIT, shift=VideoShift(0, 200)),
            _view(VideoCellViewMode.FIT, scale=3.0, shift=VideoShift(400, -100)),
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
            VideoCellViewMode.FIT, shift=VideoShift(0, -5000), is_shift_past_edges=True
        )

        assert calc_view_shift(VIDEO, SQUARE, view) == VideoShift(0, -960)

    def test_it_is_held_within_the_edges_again_once_not_let_past(self):
        view = _view(VideoCellViewMode.FIT, shift=VideoShift(0, -960))

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
                VideoCellViewMode.FIT,
                shift=VideoShift(0, -5000),
                is_shift_past_edges=True,
            ),
            _view(scale=3.0, shift=VideoShift(5000, 5000), is_shift_past_edges=True),
            _view(VideoCellViewMode.STRETCH, scale=1.5, anchor=VideoAnchor.BOTTOM),
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
            _view(VideoCellViewMode.FIT, crop=VideoCrop(0, 300, 900, 0)),
            _view(
                VideoCellViewMode.FIT,
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
        assert calc_view_step(VIDEO, SQUARE, _view(VideoCellViewMode.FIT)) == (96, 54)

    def test_takes_each_way_on_its_own(self):
        # zoomed out of a tall pane: bigger across, smaller down
        view = _view(VideoCellViewMode.FIT, scale=1.5)

        across, down = calc_view_step(VIDEO, (900, 2000), view)

        assert across < 0 < down

    def test_is_the_same_past_the_edges(self):
        """Less of it is on show out there, but a press goes as far."""

        view = _view(VideoCellViewMode.FIT, is_shift_past_edges=True)
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
        view = _view(VideoCellViewMode.FIT, shift=VideoShift(0, -70))

        assert calc_moved_shift(VIDEO, SQUARE, view, (0, 1)) == VideoShift(0, -54)
        assert calc_moved_shift(VIDEO, SQUARE, view, (0, -1)) == VideoShift(0, -108)

    def test_is_held_where_the_picture_stops(self):
        view = _view(VideoCellViewMode.FIT, shift=VideoShift(0, 400))

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


class TestViewBorders:
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


# stored 320x360, its pixels twice as wide as tall: a 640x360 picture
WIDE_PIXELS = (320, 360)


class TestPixelAspect:
    """A video's pixels need not be square: the picture has the shape they
    give it, and the crop and the shift are still in its own pixels."""

    def test_wide_pixels_make_a_wide_picture(self):
        placement = calc_view_placement(
            WIDE_PIXELS, (1280, 720), _view(VideoCellViewMode.FIT), pixel_aspect=2
        )

        assert placement.source == _approx((0, 0, 320, 360))
        assert placement.target == _approx((0, 0, 1280, 720))

    def test_a_dvb_picture_is_16_9(self):
        placement = calc_view_placement(
            (720, 576), PANE, _view(VideoCellViewMode.FIT), pixel_aspect=64 / 45
        )

        assert placement.target == _approx((0, 0, 1600, 900))

    def test_covering_a_pane_cuts_the_picture_by_its_shape(self):
        # 640x360 covers 900x900 at 1600x900: 180 of the 320 pixels on show
        placement = calc_view_placement(WIDE_PIXELS, SQUARE, _view(), pixel_aspect=2)

        assert placement.source == _approx((70, 0, 180, 360))

    def test_the_crop_is_in_the_video_s_own_pixels(self):
        # 240x360 kept is 480x360 shown, 4:3
        view = _view(VideoCellViewMode.FIT, crop=VideoCrop(40, 0, 40, 0))

        placement = calc_view_placement(WIDE_PIXELS, (1280, 720), view, pixel_aspect=2)

        assert placement.target == _approx((160, 0, 960, 720))

    def test_turned_the_wide_picture_is_tall(self):
        placement = calc_view_placement(
            WIDE_PIXELS,
            (900, 1600),
            _view(VideoCellViewMode.FIT),
            VideoTransform.ROTATE_90,
            pixel_aspect=2,
        )

        assert placement.target == _approx((0, 0, 900, 1600))

    def test_one_of_other_pixels_follows_to_the_same_place(self):
        """10 wide pixels are 20 square ones of the same picture."""

        leader = _view(scale=2.0, shift=VideoShift(-10, -5))
        shared = calc_shared_view(WIDE_PIXELS, PANE, leader, pixel_aspect=2)

        followed = calc_followed_view((640, 360), PANE, _view(), shared)

        assert followed.shift == VideoShift(-20, -5)


class TestAspectRatio:
    """An aspect ratio picked is the shape the whole picture is shown in,
    as it is shown: the pixels are made as wide as that takes."""

    @pytest.mark.parametrize(
        ("text", "ratio"),
        [("16:9", 16 / 9), ("2.35:1", 2.35), ("1:1", 1.0), ("4:3", 4 / 3)],
    )
    def test_reads_a_ratio(self, text, ratio):
        assert parse_aspect_ratio(text) == pytest.approx(ratio)

    @pytest.mark.parametrize(
        "text", ["", "16", "16:0", "a:b", ":9", "16:9:1", "-16:9", "100:1", "nan:1"]
    )
    def test_anything_else_is_none(self, text):
        assert parse_aspect_ratio(text) is None

    def test_none_picked_is_the_video_s_own(self):
        assert calc_shown_pixel_aspect((720, 576), None, "", 64 / 45) == 64 / 45

    def test_without_a_frame_it_is_the_video_s_own(self):
        assert calc_shown_pixel_aspect((0, 0), None, "16:9", 1.0) == 1.0

    def test_a_4_3_frame_shown_16_9(self):
        pixel_aspect = calc_shown_pixel_aspect((1440, 1080), None, "16:9", 1.0)

        placement = calc_view_placement(
            (1440, 1080), PANE, _view(VideoCellViewMode.FIT), pixel_aspect=pixel_aspect
        )

        assert placement.target == _approx((0, 0, 1600, 900))

    def test_the_video_s_own_pixels_make_no_difference(self):
        assert calc_shown_pixel_aspect(
            WIDE_PIXELS, None, "4:3", 2.0
        ) == calc_shown_pixel_aspect(WIDE_PIXELS, None, "4:3", 1.0)

    def test_turned_it_is_still_the_shape_picked(self):
        """1920x1080 turned is shown 1080x1920, picked 16:9 it is 16:9."""

        pixel_aspect = calc_shown_pixel_aspect(
            VIDEO, VideoTransform.ROTATE_270, "16:9", 1.0
        )

        placement = calc_view_placement(
            VIDEO,
            PANE,
            _view(VideoCellViewMode.FIT),
            VideoTransform.ROTATE_270,
            pixel_aspect=pixel_aspect,
        )

        assert placement.target == _approx((0, 0, 1600, 900))


class TestCropRatio:
    """A crop shape cuts the picture to it, as it is shown, by margins
    taken evenly off the two sides it is too long between."""

    def test_a_wide_frame_cut_to_4_3_loses_its_sides(self):
        assert calc_ratio_crop(VIDEO, None, "4:3") == VideoCrop(240, 0, 240, 0)

    def test_a_frame_cut_wider_loses_its_top_and_bottom(self):
        """1920 / 2.35 is 817 rows kept, and the odd one goes at the bottom."""

        assert calc_ratio_crop(VIDEO, None, "2.35:1") == VideoCrop(0, 131, 0, 132)

    def test_one_of_that_shape_already_is_not_cut(self):
        assert calc_ratio_crop(VIDEO, None, "16:9") == NO_CROP

    def test_none_picked_or_no_frame_is_no_cut(self):
        assert calc_ratio_crop(VIDEO, None, "") == NO_CROP
        assert calc_ratio_crop((0, 0), None, "4:3") == NO_CROP

    def test_wide_pixels_are_cut_as_they_are_shown(self):
        """720x576 of 64:45 pixels is 1024x576, 16:9 already."""

        assert calc_ratio_crop((720, 576), None, "16:9", 64 / 45) == NO_CROP
        assert calc_ratio_crop((720, 576), None, "4:3", 64 / 45) == VideoCrop(
            90, 0, 90, 0
        )

    def test_the_aspect_ratio_picked_is_cut_from(self):
        """A 4:3 frame shown 16:9, then cut to 4:3, loses its sides."""

        pixel_aspect = calc_shown_pixel_aspect((1440, 1080), None, "16:9", 1.0)

        assert calc_ratio_crop((1440, 1080), None, "4:3", pixel_aspect) == VideoCrop(
            180, 0, 180, 0
        )

    def test_turned_it_is_cut_as_shown(self):
        """1920x1080 turned is shown 1080x1920: a square loses top and
        bottom on screen, which are the frame's own top and bottom."""

        crop = calc_ratio_crop(VIDEO, VideoTransform.ROTATE_90, "1:1")

        placement = calc_view_placement(
            VIDEO,
            PANE,
            _view(VideoCellViewMode.FIT, crop=crop),
            VideoTransform.ROTATE_90,
        )

        assert crop.Left == crop.Right == 0
        assert crop.Top == crop.Bottom
        _, _, width, height = placement.target
        assert width / height == pytest.approx(1, abs=0.01)

    @pytest.mark.parametrize("ratio", ["16:10", "1.85:1", "2.39:1", "5:3", "1:1"])
    def test_the_picture_is_shown_that_shape(self, ratio):
        crop = calc_ratio_crop(VIDEO, None, ratio)

        placement = calc_view_placement(
            VIDEO, PANE, _view(VideoCellViewMode.FIT, crop=crop)
        )

        _, _, width, height = placement.target
        assert width / height == pytest.approx(parse_aspect_ratio(ratio), rel=0.005)


@pytest.mark.parametrize(
    ("crop", "transform", "pixel_aspect", "shape"),
    [
        (NO_CROP, VideoTransform.NONE, 1, 16 / 9),
        (NO_CROP, VideoTransform.ROTATE_90, 1, 9 / 16),
        (NO_CROP, VideoTransform.ROTATE_180, 1, 16 / 9),
        (VideoCrop(420, 0, 420, 0), VideoTransform.NONE, 1, 1),
        (NO_CROP, VideoTransform.NONE, 0.75, 4 / 3),
    ],
    ids=["as_is", "turned", "upside_down", "cut_square", "squeezed_pixels"],
)
def test_picture_shape(crop, transform, pixel_aspect, shape):
    assert calc_picture_shape(VIDEO, crop, transform, pixel_aspect) == pytest.approx(
        shape
    )


def test_picture_shape_of_no_frame():
    assert calc_picture_shape((0, 0), NO_CROP, VideoTransform.NONE) is None
