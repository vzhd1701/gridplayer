"""
Generate LANGUAGES = ( ... ) block for Crowdin project into gridplayer/params/languages.py
Only includes authors who translated more than MIN_WORDS words
"""

import argparse
import sys
import time
import yaml
import requests
import pprint
from pathlib import Path


API_BASE = "https://api.crowdin.com/api/v2"


def load_credentials(identity_path):
    with open(identity_path) as f:
        cfg = yaml.safe_load(f) or {}

    token = cfg.get("api_token")
    project_id = cfg.get("project_id")

    return token, str(project_id)


def api(method, url, token, **kwargs):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.request(method, url, headers=headers, timeout=90, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else {}


def get_project_progress(token, project_id):
    """Returns list of {languageId, translationProgress, language: {...}}"""
    data = api(
        "GET", f"{API_BASE}/projects/{project_id}/languages/progress?limit=500", token
    )
    return data["data"]


def generate_report(token, project_id):
    payload = {
        "name": "top-members",
        "schema": {
            "unit": "words",
            "format": "json",
            "dateFrom": "2010-01-01T00:00:00+00:00",
            "dateTo": "2030-01-01T00:00:00+00:00",
        },
    }
    resp = api("POST", f"{API_BASE}/projects/{project_id}/reports", token, json=payload)
    return resp["data"]["identifier"]


def wait_report(token, project_id, report_id, timeout=400):
    start = time.time()
    while time.time() - start < timeout:
        data = api(
            "GET", f"{API_BASE}/projects/{project_id}/reports/{report_id}", token
        )
        status = data["data"]["status"]
        if status == "finished":
            return
        if status in ("failed", "canceled"):
            raise RuntimeError(f"Report {report_id} failed: {status}")
        time.sleep(3)
    raise TimeoutError("Report timed out")


def download_report(token, project_id, report_id):
    data = api(
        "GET", f"{API_BASE}/projects/{project_id}/reports/{report_id}/download", token
    )
    url = data["data"]["url"]
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()["data"]


def make_code(lang_obj, lang_id):
    """Turn Crowdin language into the style used in the example (en_US, zh_CN ...)"""
    locale = lang_obj.get("locale") or lang_id
    return locale.replace("-", "_")


def get_languages_top(token, project_id, min_words, admin_username):
    print(f"# Project {project_id}  |  min words = {min_words}\n", file=sys.stderr)

    progress_list = get_project_progress(token, project_id)

    # {
    #  'data': {
    #    'languageId': 'ar',
    #    'language': {
    #      'id': 'ar',
    #      'name': 'Arabic',
    #      'editorCode': 'ar',
    #      'twoLettersCode': 'ar',
    #      'threeLettersCode': 'ara',
    #      'locale': 'ar-SA',
    #      'androidCode': 'ar-rSA',
    #      'bcp47Code': 'b+ar+SA',
    #      'osxCode': 'ar.lproj',
    #      'osxLocale': 'ar',
    #      'pluralCategoryNames': [
    #        'zero',
    #        'one',
    #        'two',
    #        'few',
    #        'many',
    #        'other'
    #      ],
    #      'pluralRules': '(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 && n%100<=99 ? 4 : 5)',
    #      'pluralExamples': [
    #        '0',
    #        '1',
    #        '2',
    #        '3-10, 103-110, 203-210...',
    #        '11-99, 111-199, 211-299...',
    #        '100-102, 200-202, 300-302...; 0.2, 1.07, 2.94, 3.81, 11.68, 100.55...'
    #      ],
    #      'textDirection': 'rtl',
    #      'dialectOf': None
    #    },
    #    'words': {
    #      'total': 875,
    #      'translated': 740,
    #      'preTranslateAppliedTo': 0,
    #      'approved': 740
    #    },
    #    'phrases': {
    #      'total': 305,
    #      'translated': 237,
    #      'preTranslateAppliedTo': 0,
    #      'approved': 237
    #    },
    #    'translationProgress': 84,
    #    'approvalProgress': 84,
    #    'qaChecksStatus': {
    #      'total': 237,
    #      'inProgress': 0,
    #      'passed': 237,
    #      'failed': 0
    #    }
    #  }
    # },

    report_id = generate_report(token, project_id)
    wait_report(token, project_id, report_id)
    report_members = download_report(token, project_id, report_id)

    # {
    #  'user': {
    #    'id': '12345',
    #    'username': 'Username',
    #    'fullName': 'Full Name',
    #    'avatarUrl': '...',
    #    'joined': '2022-07-17 00:23:10'
    #  },
    #  'languages': [
    #    {
    #      'id': 'ko',
    #      'name': 'Korean'
    #    }
    #  ],
    #  'translated': 886,
    #  'target': 920,
    #  'approved': 0,
    #  'voted': 0,
    #  'positiveVotes': 0,
    #  'negativeVotes': 0,
    #  'winning': 874
    # },

    result = {"en_US": {"completion": 100, "authors": []}}

    for item in progress_list:
        lang_id = item["data"]["languageId"]
        completion = item["data"]["approvalProgress"]
        lang_obj = item["data"].get("language", {})
        code = make_code(lang_obj, lang_id)

        if completion == 0:
            continue

        print(f"→ {code} ({lang_id}) ...", end=" ", flush=True, file=sys.stderr)

        authors = []

        for m in report_members:
            words = m.get("translated") or 0
            if words <= min_words:
                continue

            language_ids = {lang["id"] for lang in m.get("languages", [])}
            if not language_ids:
                continue

            user = m.get("user") or {}
            username = user.get("username")
            full_name = user.get("fullName") or username
            if not username or username == admin_username:
                continue

            profile = f"https://crowdin.com/profile/{username}"

            if lang_id in language_ids:
                authors.append({"full_name": full_name, "profile_url": profile})

        # keep order of contribution (already sorted by report)
        print(f"{len(authors)} authors", file=sys.stderr)

        result[code] = {
            "completion": completion,
            "authors": authors,
        }

    return result


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--min-words", type=int, default=10)
    parser.add_argument("--identity")
    parser.add_argument("--admin-username")
    parser.add_argument("out", type=Path)

    args = parser.parse_args()

    token, project_id = load_credentials(args.identity)

    languages_top = get_languages_top(
        token, project_id, args.min_words, args.admin_username
    )

    with args.out.open("w", encoding="utf-8") as f:
        print(f"LANGUAGES_CONTRIB = ", end=" ", file=f)
        pprint.pprint(languages_top, stream=f)

    print(f"Languages contributors list updated at {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
