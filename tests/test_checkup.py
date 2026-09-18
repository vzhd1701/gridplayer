"""The part of a checkup that is the same whatever it is checking.

What each one finds is its own business and tested with it. What is left
is how a run reads once it is over, which is the thing somebody pastes
into a bug report, so it has to say as much about a run that was called
off as about one that finished.
"""

from gridplayer.utils.checkup import CheckResult, CheckStatus, report_text


class TestTheReport:
    def test_it_is_headed_with_whatever_was_run(self):
        report = report_text("Network checkup", [])

        assert report.splitlines()[0].startswith("Network checkup - ")

    def test_a_run_that_was_stopped_reports_as_far_as_it_got(self):
        rows = [
            ("Step one", CheckResult(CheckStatus.PASSED, "fine")),
            ("Step two", None),
        ]

        report = report_text("A checkup", rows)

        assert "[ ok ] Step one: fine" in report
        assert "[ -- ] Step two: Not run" in report

    def test_a_hint_travels_with_the_step_it_belongs_to(self):
        rows = [("Step one", CheckResult(CheckStatus.FAILED, "broke", "try this"))]

        assert "    try this" in report_text("A checkup", rows)

    def test_every_way_a_step_can_come_out_has_a_tag_of_its_own(self):
        rows = [(status.value, CheckResult(status, "said")) for status in CheckStatus]

        tags = [
            line.split(maxsplit=1)[0] for line in report_text("x", rows).split("\n")[2:]
        ]

        assert len(set(tags)) == len(CheckStatus)
