"""The patterns table, driven the way a person drives it.

Its buttons are the part worth clicking rather than calling: a clicked
signal carries whether the button is checked, and a slot that takes a row
of data would be handed that bool instead.
"""

import pytest

from gridplayer.models.resolver_patterns import (
    ResolverPattern,
    ResolverPatterns,
    ResolverPatternType,
)
from gridplayer.params.static import URLResolver
from gridplayer.widgets.resolver_patterns_list import ResolverPatternsList


def _pattern(pattern="*.example.com"):
    return ResolverPattern(
        pattern=pattern,
        pattern_type=ResolverPatternType.WILDCARD_HOST,
        resolver=URLResolver.YT_DLP,
    )


@pytest.fixture
def patterns():
    widget = ResolverPatternsList()

    yield widget

    widget.deleteLater()


class TestTheButtons:
    def test_add_gives_a_row_to_fill_in(self, patterns):
        patterns.add_button.click()

        assert patterns.table.rowCount() == 1
        assert patterns.rows_data()[0].pattern == ""

    def test_add_twice_does_not_leave_two_blank_rows(self, patterns):
        patterns.add_button.click()
        patterns.add_button.click()

        assert patterns.table.rowCount() == 1

    def test_remove_is_not_offered_with_nothing_picked(self, patterns):
        assert not patterns.remove_button.isEnabled()

    def test_remove_takes_the_selected_row_out(self, patterns):
        patterns.setDataRows(ResolverPatterns([_pattern()]))

        patterns.table.selectRow(0)
        patterns.remove_button.click()

        assert patterns.table.rowCount() == 0


class TestWhatIsLoadedComesBack:
    def test_a_row_survives_the_round_trip(self, patterns):
        patterns.setDataRows(ResolverPatterns([_pattern("*.example.com")]))

        row = patterns.rows_data()[0]

        assert row.pattern == "*.example.com"
        assert row.pattern_type is ResolverPatternType.WILDCARD_HOST
        assert row.resolver is URLResolver.YT_DLP

    def test_several_of_them_keep_their_order(self, patterns):
        patterns.setDataRows(
            ResolverPatterns([_pattern("one.example"), _pattern("two.example")])
        )

        assert [row.pattern for row in patterns.rows_data()] == [
            "one.example",
            "two.example",
        ]
