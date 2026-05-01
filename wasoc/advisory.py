"""SendGrid advisory draft creation for WA SOC advisories."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from sendgrid import SendGridAPIClient

SITE_URL = "https://soc.cyber.wa.gov.au"
ADVISORY_DIR = Path("docs/advisories")
ADVISORY_BASE_URL = f"{SITE_URL}/advisories/"
HUGO_EMAIL_ROOT = Path("site")
SENDGRID_LIST_ID = "fdeb76e9-0895-4b5e-b929-4022f71cb16d"
SENDGRID_SENDER_ID = 5228194
TITLE_MAX_LENGTH = 100
AUTO_LOOKBACK_DAYS = 5


@dataclass(frozen=True)
class Advisory:
    uid: str
    title: str
    path: Path

    @property
    def url(self) -> str:
        return f"{ADVISORY_BASE_URL}{self.path.stem}/"


def document_title(markdown_text: str) -> str | None:
    """Return the first level-1 markdown heading from text."""
    for line in markdown_text.lstrip("\ufeff").splitlines():
        if line.startswith("# "):
            return line.lstrip("#").strip()
    return None


def sendgrid_client() -> SendGridAPIClient:
    """Return a SendGrid client, failing closed if the API key is missing."""
    api_key = os.environ.get("SENDGRID_API")
    if not api_key:
        raise SystemExit("ERROR: SENDGRID_API environment variable is not set")
    return SendGridAPIClient(api_key)


def advisory_uid_from_name(name: str) -> str:
    match = re.match(r"(?P<uid>\d{11})-", Path(name).name)
    if not match:
        raise ValueError(f"Could not find 11-digit advisory UID in {name}")
    return match.group("uid")


def advisory_uid_from_url(url: str) -> str:
    match = re.search(r"/advisories/(?P<uid>\d{11})-", url)
    if not match:
        raise ValueError(f"Could not find advisory UID in {url}")
    return match.group("uid")


def advisory_path_for_uid(uid: str) -> Path:
    try:
        return next(ADVISORY_DIR.glob(f"{uid}-*.md"))
    except StopIteration as exc:
        raise FileNotFoundError(f"No advisory markdown found for UID {uid}") from exc


def parse_advisory(path: Path) -> Advisory:
    """Return advisory metadata from markdown content."""
    markdown_text = path.read_text(encoding="utf-8-sig")
    title = document_title(markdown_text)
    if not title:
        raise ValueError("Advisory title not found")
    title = re.sub(r"\s+-\s+\d{11}$", "", title).strip()
    if len(title) >= TITLE_MAX_LENGTH:
        raise ValueError(
            f"Advisory '{title}' title length is {len(title)} characters; "
            f"it must be less than {TITLE_MAX_LENGTH} characters"
        )
    return Advisory(advisory_uid_from_name(path.name), title, path)


def rendered_email_path(advisory: Advisory) -> Path:
    return HUGO_EMAIL_ROOT / "advisories" / advisory.path.stem / "email.html"


def render_email(advisory: Advisory) -> str:
    path = rendered_email_path(advisory)
    if not path.is_file():
        raise FileNotFoundError(
            f"Rendered Hugo email output not found: {path}. "
            "Run `hugo --gc --destination site` first."
        )
    return path.read_text(encoding="utf-8")


def email_lookup(client: SendGridAPIClient, uid: str) -> tuple[bool, str, str | None]:
    response = client.client.marketing.singlesends.search.post(
        request_body={"name": uid}
    )
    results = json.loads(response.body).get("result", [])
    if not results:
        print("NOTE: No existing advisory found")
        return False, "", None

    result = results[0]
    name = result["name"]
    result_id = result.get("id")
    print(
        f"\nNOTE: The advisory '{name}' already exists and was sent at "
        f"'{result.get('send_at', '')}' with '{result.get('status', '')}' status. "
        f"SendGrid ID: {result_id}"
    )
    return True, name, result_id


def email_delete(client: SendGridAPIClient, uid: str) -> None:
    exists, name, result_id = email_lookup(client, uid)
    if not exists or not result_id:
        raise SystemExit(f"No existing advisory found. Cannot delete advisory {uid}")

    client.client.marketing.singlesends._(result_id).delete()
    print(f"NOTE: The advisory {name} was deleted")


def email_campaign(client: SendGridAPIClient, advisory: Advisory) -> None:
    data = {
        "name": f"{advisory.uid} - TLP CLEAR - {advisory.title}",
        "categories": ["wasoc-advisory"],
        "send_to": {"list_ids": [SENDGRID_LIST_ID], "segment_ids": [], "all": False},
        "email_config": {
            "subject": f"Cyber Security Advisory - TLP CLEAR - {advisory.title}",
            "html_content": render_email(advisory),
            "generate_plain_content": True,
            "editor": "design",
            "suppression_group_id": -1,
            "custom_unsubscribe_url": None,
            "sender_id": SENDGRID_SENDER_ID,
        },
    }
    client.client.marketing.singlesends.post(request_body=data)
    print(
        f"\nAdvisory: {advisory.uid} - TLP CLEAR - {advisory.title} "
        "was uploaded to SendGrid for review"
    )


def send_campaign(client: SendGridAPIClient, paths: list[Path]) -> None:
    for path in paths:
        print(f"\nCollecting advisory data from source: {path}")
        advisory = parse_advisory(path)
        exists, _, _ = email_lookup(client, advisory.uid)
        if exists:
            print(
                "\nERROR: Advisory already exists. Requested advisory will be skipped."
            )
            print("\n-------------------------")
            continue
        email_campaign(client, advisory)


def paths_from_source(source: str) -> list[Path]:
    if source.startswith(ADVISORY_BASE_URL):
        return [advisory_path_for_uid(advisory_uid_from_url(source))]

    path = Path(source)
    if path.suffix == ".md":
        return (
            [path]
            if path.is_file()
            else [advisory_path_for_uid(advisory_uid_from_name(path.name))]
        )

    raise ValueError(f"Input {source} is not a SOC advisory URL or markdown file")


def latest_advisory_paths(count: int) -> list[Path]:
    if count < 1:
        raise ValueError("Count must be at least 1")
    return sorted(ADVISORY_DIR.glob("*.md"), key=lambda item: item.name)[-count:]


def recent_advisory_paths(days: int = AUTO_LOOKBACK_DAYS) -> list[Path]:
    lookback_dates = {
        (dt.date.today() - dt.timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(days)
    }
    return [
        path
        for path in sorted(ADVISORY_DIR.glob("*.md"), key=lambda item: item.name)
        if path.name[:8] in lookback_dates
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--auto", "-a", action="store_true", help="create drafts for recent advisories"
    )
    mode.add_argument(
        "--bulk",
        "-b",
        nargs="?",
        const=0,
        type=int,
        metavar="COUNT",
        help="create drafts for the latest COUNT advisories",
    )
    mode.add_argument(
        "source", nargs="?", help="SOC advisory URL or advisory markdown file"
    )
    parser.add_argument(
        "--action",
        "-x",
        choices=("new", "update", "delete"),
        default="new",
        help="operation for a manual source (default: new)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        client = sendgrid_client()
        if args.auto:
            paths = recent_advisory_paths()
            if not paths:
                print(
                    "NOTE: No recent advisories found for automatic "
                    "SendGrid draft creation"
                )
            send_campaign(client, paths)
            return 0

        if args.bulk is not None:
            count = args.bulk or int(
                input(
                    "To bulk create SendGrid advisories, enter the "
                    "number of latest advisories: "
                )
            )
            send_campaign(client, latest_advisory_paths(count))
            return 0

        paths = paths_from_source(args.source)
        uid = paths[0].name.split("-", 1)[0]
        if args.action in {"delete", "update"}:
            email_delete(client, uid)
        if args.action in {"new", "update"}:
            send_campaign(client, paths)
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
