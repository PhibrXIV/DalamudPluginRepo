import json
import os
import requests
from time import time
from urllib.parse import urlparse

DOWNLOAD_URL_TEMPLATE = "{repo_url}/releases/download/v{version}/latest.zip"
GITHUB_RELEASES_API_URL = "https://api.github.com/repos/{owner}/{repo}/releases/tags/v{version}"

DEFAULTS = {
    "IsHide": False,
    "IsTestingExclusive": False,
    "ApplicableVersion": "any",
}

DUPLICATES = {
    "DownloadLinkInstall": ["DownloadLinkTesting", "DownloadLinkUpdate"],
}

TRIMMED_KEYS = [
    "Author",
    "Name",
    "Punchline",
    "Description",
    "Changelog",
    "InternalName",
    "AssemblyVersion",
    "RepoUrl",
    "ApplicableVersion",
    "Tags",
    "CategoryTags",
    "DalamudApiLevel",
    "IconUrl",
    "ImageUrls",
]

def main():
    manifests = extract_manifests()
    manifests = [trim_manifest(m) for m in manifests]
    add_extra_fields(manifests)
    get_last_updated_times(manifests)
    # keep output stable by sorting
    manifests.sort(key=lambda m: (m.get("InternalName", ""), m.get("AssemblyVersion", "")))
    write_master(manifests)

def extract_manifests():
    """Collect all plugin manifests from ./plugins/*/*.json."""
    manifests = []
    for dirpath, _, filenames in os.walk("./plugins"):
        plugin_name = dirpath.split("/")[-1]
        if not filenames or f"{plugin_name}.json" not in filenames:
            continue
        with open(f"{dirpath}/{plugin_name}.json", "r", encoding="utf-8") as f:
            manifests.append(json.load(f))
    return manifests

def add_extra_fields(manifests):
    for manifest in manifests:
        version = manifest["AssemblyVersion"]
        repo_url = manifest["RepoUrl"].rstrip("/")

        # Download links
        manifest["DownloadLinkInstall"] = DOWNLOAD_URL_TEMPLATE.format(
            repo_url=repo_url, version=version
        )

        # Defaults
        for k, v in DEFAULTS.items():
            manifest.setdefault(k, v)

        # Duplicate fields
        for source, keys in DUPLICATES.items():
            for k in keys:
                manifest.setdefault(k, manifest[source])

        # Download count from GitHub API
        owner, repo = parse_owner_repo(repo_url)
        manifest["DownloadCount"] = get_release_download_count(owner, repo, version)

def parse_owner_repo(repo_url: str):
    """
    Given a GitHub repo URL like https://github.com/Owner/Repo,
    return ("Owner", "Repo").
    """
    p = urlparse(repo_url)
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        raise ValueError(f"RepoUrl is not a valid GitHub repo URL: {repo_url}")
    return parts[0], parts[1]

def _gh_headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("PAT")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers

def get_release_download_count(owner: str, repo: str, version: str) -> int:
    """
    Sum the download_count of all assets for the tag v{version}.
    Returns 0 on any error.
    """
    url = GITHUB_RELEASES_API_URL.format(owner=owner, repo=repo, version=version)
    try:
        r = requests.get(url, headers=_gh_headers(), timeout=15)
        if r.status_code != 200:
            return 0
        data = r.json()
        return sum(asset.get("download_count", 0) for asset in data.get("assets", []))
    except Exception:
        return 0

def get_last_updated_times(manifests):
    """
    Preserve LastUpdate if AssemblyVersion hasn't changed compared to the existing pluginmaster.json.
    Otherwise set to current time().
    """
    previous_manifests = []
    try:
        with open("pluginmaster.json", "r", encoding="utf-8") as f:
            previous_manifests = json.load(f)
    except FileNotFoundError:
        previous_manifests = []
    except json.JSONDecodeError:
        previous_manifests = []

    prev_map = {
        m.get("InternalName"): m for m in previous_manifests if "InternalName" in m
    }

    now_str = str(int(time()))
    for manifest in manifests:
        manifest["LastUpdate"] = now_str
        prev = prev_map.get(manifest.get("InternalName"))
        if prev and prev.get("AssemblyVersion") == manifest.get("AssemblyVersion"):
            manifest["LastUpdate"] = prev.get("LastUpdate", now_str)

def write_master(master):
    with open("pluginmaster.json", "w", encoding="utf-8") as f:
        json.dump(master, f, indent=4, ensure_ascii=False)

def trim_manifest(plugin):
    return {k: plugin[k] for k in TRIMMED_KEYS if k in plugin}

if __name__ == "__main__":
    main()
