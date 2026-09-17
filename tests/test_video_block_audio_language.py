"""Choosing which language a dubbed video plays in."""

import logging

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.stream import STREAM_QUALITY_AUTO, Stream, Streams
from gridplayer.models.video import Video
from gridplayer.params.static import AudioTrackMode
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _dubbed_ladder(original="en"):
    return Streams(
        {
            f"{height}p ({language})": Stream(
                url=f"http://host/{height}-{language}",
                protocol="http",
                language=language,
                is_original_language=language == original,
            )
            for height in (360, 720)
            for language in ("cop", "tlh", "en")
        }
    )


def _block(mocker, languages="", streams=None):
    block = mocker.Mock()
    block._log = logging.getLogger("test")
    block.streams = _dubbed_ladder() if streams is None else streams
    block._language_variants = VideoBlock._language_variants.fget(block)
    block.video_params = Video(uri="http://example.com/a.mp4")
    block.video_params.audio_languages = languages
    block.video_params.stream_quality = STREAM_QUALITY_AUTO
    return block


def _language(block):
    block._language_variants = VideoBlock._language_variants.fget(block)
    return VideoBlock.audio_language.fget(block)


def _options(block):
    return VideoBlock.audio_language_options.fget(block)


def _ladder(block):
    block.audio_language = _language(block)
    return VideoBlock.stream_ladder.fget(block)


def test_the_preferred_language_is_the_one_played(mocker):
    assert _language(_block(mocker, "tlh")) == "tlh"


def test_a_language_may_be_asked_for_by_name(mocker):
    assert _language(_block(mocker, "Klingon")) == "tlh"


def test_the_first_language_asked_for_that_is_offered_wins(mocker):
    assert _language(_block(mocker, "de, cop, en")) == "cop"


def test_a_video_falls_back_to_the_language_it_was_made_in(mocker):
    """Not to whichever dub the site happened to list first."""

    block = _block(mocker, "de")

    assert _language(block) == "en"


def test_an_unmarked_original_falls_back_to_the_first_offered(mocker):
    block = _block(mocker, "de", streams=_dubbed_ladder(original=None))

    assert _language(block) == "cop"


def test_no_preference_still_plays_the_original(mocker):
    assert _language(_block(mocker, "")) == "en"


def test_a_ladder_with_one_language_is_not_narrowed(mocker):
    streams = Streams(
        {f"{h}p": Stream(url="u", protocol="http", language="en") for h in (360, 720)}
    )

    assert _language(_block(mocker, "en", streams=streams)) is None


def test_a_ladder_with_no_languages_is_not_narrowed(mocker):
    streams = Streams({f"{h}p": Stream(url="u", protocol="http") for h in (360, 720)})

    assert _language(_block(mocker, "en", streams=streams)) is None


def test_an_unresolved_video_has_no_language(mocker):
    assert _language(_block(mocker, "en", streams=Streams())) is None


def test_the_ladder_holds_only_the_language_being_played(mocker):
    block = _block(mocker, "tlh")

    assert list(_ladder(block)) == ["360p (tlh)", "720p (tlh)"]


def test_the_whole_ladder_shows_when_there_is_one_language(mocker):
    streams = Streams({f"{h}p": Stream(url="u", protocol="http") for h in (360, 720)})
    block = _block(mocker, "en", streams=streams)

    assert list(_ladder(block)) == ["360p", "720p"]


def test_switching_language_reloads_at_the_same_size(mocker):
    block = _block(mocker, "en")
    block.video_params.stream_quality = "720p (en)"
    block._audio_language_playing = "en"

    VideoBlock.set_audio_language(block, "tlh")

    assert block.video_params.audio_language == "tlh"
    assert block.video_params.audio_track_mode is AudioTrackMode.EXPLICIT
    block.reset.assert_called_once()
    block.load_stream_quality.assert_called_once_with("720p (en)")


def test_switching_language_leaves_the_preference_list_alone(mocker):
    """The list is what "Preferred" follows, and picking one is not that."""

    block = _block(mocker, "en, de")
    block._audio_language_playing = "en"

    VideoBlock.set_audio_language(block, "tlh")

    assert block.video_params.audio_languages == "en, de"


def test_an_explicit_language_outranks_the_preference(mocker):
    block = _block(mocker, "en")
    block.video_params.audio_language = "cop"
    block.video_params.audio_track_mode = AudioTrackMode.EXPLICIT

    assert _language(block) == "cop"


def test_an_explicit_language_the_video_no_longer_offers_is_dropped(mocker):
    """Another ladder, another set of languages; the preference stands in."""

    block = _block(mocker, "en")
    block.video_params.audio_language = "de"
    block.video_params.audio_track_mode = AudioTrackMode.EXPLICIT

    assert _language(block) == "en"


def test_going_back_to_preferred_clears_the_pick(mocker):
    block = _block(mocker, "en")
    block.video_params.audio_language = "tlh"
    block.video_params.audio_track_mode = AudioTrackMode.EXPLICIT
    block._audio_language_playing = "tlh"

    VideoBlock.set_audio_language(block, None)

    assert block.video_params.audio_language is None
    assert block.video_params.audio_track_mode is AudioTrackMode.PREFERRED
    block.reset.assert_called_once()


def test_switching_language_calls_off_a_pending_quality_adapt(mocker):
    """The rung it was counting towards is not on the new ladder."""

    block = _block(mocker, "en")
    block._audio_language_playing = "en"

    VideoBlock.set_audio_language(block, "cop")

    block._quality_adapt_timer.stop.assert_called_once()


def test_switching_to_the_language_already_playing_does_nothing(mocker):
    block = _block(mocker, "en")
    block._audio_language_playing = "tlh"
    block.video_params.audio_language = "tlh"
    block.video_params.audio_track_mode = AudioTrackMode.EXPLICIT
    block.audio_language = _language(block)

    VideoBlock.set_audio_language(block, "tlh")

    block.reset.assert_not_called()
    block.load_stream_quality.assert_not_called()


def test_a_language_picked_by_hand_outlives_the_playlist(tmp_path):
    """The pick is stored as the language, not as the rung it resolved to.

    A rung is named differently on every ladder, and the ladder is
    resolved afresh every time the video is opened.
    """

    from gridplayer.models.playlist import Playlist

    video = Video(uri="http://example.com/a.mp4")
    video.audio_languages = "tlh"
    video.stream_quality = "720p (Klingon) [avc1 3786kbps]"

    reloaded = Playlist._parse_json(Playlist(videos=[video]).dumps(), base_dir=None)

    assert reloaded.videos[0].audio_languages == "tlh"
    assert reloaded.videos[0].stream_quality == "720p (Klingon) [avc1 3786kbps]"


def _paired_stream(*languages):
    """A silent video rung with an audio track per language to pair with it."""

    audio_tracks = Streams(
        {
            f"Audio ({language}) [{bitrate}kbps]": Stream(
                url=f"http://host/a-{language}-{bitrate}",
                protocol="http_hls",
                is_audio_only=True,
                language=language,
                is_original_language=language == "en",
            )
            for language in languages
            for bitrate in (50, 128)
        }
    )

    return Stream(url="http://host/v", protocol="dash", audio_tracks=audio_tracks)


def test_languages_are_found_on_the_audio_tracks_when_the_ladder_has_none(mocker):
    """A site that pairs one ladder with several audio tracks still dubs."""

    streams = Streams({"720p": _paired_stream("en", "ja")})
    block = _block(mocker, "ja", streams=streams)

    assert _options(block) == ("en", "ja")
    assert _language(block) == "ja"


def test_only_the_chosen_language_is_handed_to_the_proxy(mocker):
    block = _block(mocker, "ja")
    stream = _paired_stream("en", "ja")

    narrowed = VideoBlock._with_audio_language(block, stream)

    assert {t.language for _, t in narrowed.audio_tracks.items()} == {"ja"}


def test_every_rendition_of_the_language_is_handed_over(mocker):
    """The proxy still gets to serve the best of them."""

    block = _block(mocker, "ja")

    narrowed = VideoBlock._with_audio_language(block, _paired_stream("en", "ja"))

    assert len(narrowed.audio_tracks) == 2


def test_a_stream_with_one_audio_language_is_handed_over_untouched(mocker):
    block = _block(mocker, "ja")
    stream = _paired_stream("en")

    assert VideoBlock._with_audio_language(block, stream) is stream


def test_a_stream_with_no_audio_tracks_is_handed_over_untouched(mocker):
    block = _block(mocker, "ja")
    stream = Stream(url="http://host/v", protocol="http")

    assert VideoBlock._with_audio_language(block, stream) is stream
