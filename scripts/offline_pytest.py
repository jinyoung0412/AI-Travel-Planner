"""Redact captured failure reports, including collection and teardown errors."""
import pytest

from scripts.offline_environment import install, redact

install()


def _sanitize(report):
    if report.longrepr:
        report.longrepr = redact(str(report.longrepr))
    report.sections = [(name, redact(content)) for name, content in report.sections]


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    _sanitize(outcome.get_result())


@pytest.hookimpl(tryfirst=True)
def pytest_collectreport(report):
    _sanitize(report)


def pytest_configure(config):
    # Local-variable dumps can include arbitrary request/provider objects.
    config.option.showlocals = False
