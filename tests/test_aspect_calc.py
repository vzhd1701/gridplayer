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
    calc_view_borders,
    calc_view_geometry,
    calc_view_placement,
    calc_view_shift,
    calc_view_step,
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
):
    return ViewParams(aspect, scale, crop, anchor, shift)


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

    def test_past_the_edges_shows_black(self):
        # 100 frame pixels is 100 * 900/1080 pane pixels
        placement = calc_view_placement(
            VIDEO,
            SQUARE,
            _view(anchor=VideoAnchor.LEFT, shift=VideoShift(100, 0)),
            is_beyond_edges=True,
        )

        assert placement.target == _approx((250 / 3, 0, 900 - 250 / 3, 900))
        assert placement.source == _approx((0, 0, 980, 1080))

    def test_moved_clear_of_the_pane_is_nothing(self):
        placement = calc_view_placement(
            VIDEO, SQUARE, _view(shift=VideoShift(0, 2000)), is_beyond_edges=True
        )

        assert placement is None

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

    def test_is_at_least_a_pixel(self):
        assert calc_view_step((10, 10), SQUARE, _view(scale=10.0)) == (-1, -1)

    def test_is_nothing_with_nothing_to_work_from(self):
        assert calc_view_step((0, 0), SQUARE, _view()) == (0, 0)


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

    def test_stretch_tiny_override_stays_in_vlc_sar_range(self):
        # Inverse of the degenerate huge-ratio case: 1x1 region in a 1px-wide
        # huge pane. The reduced fraction must still fit VLC's uint32 SAR math.
        crop = VideoCrop(1919, 1079, 0, 0)

        override, geo = calc_view_geometry(
            VIDEO, (1, 600000), _view(VideoAspect.STRETCH, crop=crop)
        )
        num, den = (int(part) for part in override.split(":"))

        assert geo == "+1919+1079+0+0"
        assert 0 < num <= (1 << 19) - 1
        assert 0 < den <= (1 << 19) - 1

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

            assert 0 < num <= (1 << 19) - 1
            assert 0 < den <= (1 << 19) - 1
            assert _shown_ratio(override, VIDEO, _borders(geometry)) == pytest.approx(
                round(target_w) / round(target_h), rel=1e-4
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
