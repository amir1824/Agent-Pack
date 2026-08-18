class PackError(Exception):
    """User-facing CLI failure."""


class CheckFailed(Exception):
    """pack check found drift; print status to stdout and exit 1."""

    def __init__(self, report: str) -> None:
        super().__init__(report)
        self.report = report
