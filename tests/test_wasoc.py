from pathlib import Path

import pytest

from wasoc.advisory import (
    advisory_uid_from_name,
    advisory_uid_from_url,
    document_title,
    parse_advisory,
    paths_from_source,
)


def test_document_title():
    text = "# Example - 20260101001\n\n## Overview\nBody text\n\n## Advice\nPatch"
    assert document_title(text) == "Example - 20260101001"


def test_advisory_uid_parsing():
    assert advisory_uid_from_name("20260430002-cPanel.md") == "20260430002"
    assert (
        advisory_uid_from_url(
            "https://soc.cyber.wa.gov.au/advisories/20260430002-cPanel/"
        )
        == "20260430002"
    )
    with pytest.raises(ValueError):
        advisory_uid_from_name("not-an-advisory.md")


def test_parse_advisory(tmp_path: Path):
    path = tmp_path / "20260430002-cPanel-Critical-Vulnerability.md"
    path.write_text(
        "# cPanel Critical Vulnerability - 20260430002\n\n"
        "## Overview\n"
        "Patch immediately.\n\n"
        "## Advice\n"
        "Update systems.",
        encoding="utf-8",
    )

    advisory = parse_advisory(path)

    assert advisory.uid == "20260430002"
    assert advisory.title == "cPanel Critical Vulnerability"
    assert advisory.url.endswith(
        "/advisories/20260430002-cPanel-Critical-Vulnerability/"
    )


def test_paths_from_existing_markdown(tmp_path: Path):
    path = tmp_path / "20260430002-cPanel.md"
    path.write_text("# title", encoding="utf-8")
    assert paths_from_source(str(path)) == [path]


def test_sendgrid_email_uses_hugo_rendered_output(tmp_path: Path, monkeypatch):
    from wasoc import advisory as advisory_module

    advisory = advisory_module.Advisory(
        uid="20260430002",
        title="cPanel Critical Vulnerability",
        path=Path("docs/advisories/20260430002-cPanel-Critical-Vulnerability.md"),
    )
    rendered = (
        tmp_path
        / "advisories"
        / "20260430002-cPanel-Critical-Vulnerability"
        / "email.html"
    )
    rendered.parent.mkdir(parents=True)
    rendered.write_text("<html>rendered by hugo</html>", encoding="utf-8")
    monkeypatch.setattr(advisory_module, "HUGO_EMAIL_ROOT", tmp_path)

    assert advisory_module.render_email(advisory) == "<html>rendered by hugo</html>"
