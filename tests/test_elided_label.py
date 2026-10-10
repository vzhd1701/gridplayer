from gridplayer.widgets.elided_label import ElidedLabel

PATH = "D:/Videos/Series/Season 1/Episode 01.mp4"


def test_the_whole_text_is_in_the_tooltip():
    assert ElidedLabel(PATH).toolTip() == PATH


def test_and_once_it_is_set_again():
    label = ElidedLabel(PATH)

    label.setText("D:/Videos")

    assert label.toolTip() == "D:/Videos"
