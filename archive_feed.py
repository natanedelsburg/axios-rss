#!/usr/bin/env python3
"""
Fetches the Kill the Newsletter Atom feed for Axios Communicators,
deduplicates entries, and writes a persistent RSS 2.0 feed that never prunes.
"""

import xml.etree.ElementTree as ET
import urllib.request
import os
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime

# --- Configuration ---
KTN_FEED_URL = "https://kill-the-newsletter.com/feeds/wp2whqxolhhcc27ve7v4.xml"
OUTPUT_FILE = "docs/feed.xml"
FEED_TITLE = "Axios Communicators"
FEED_DESCRIPTION = "Axios Communicators newsletter - archived RSS feed"
FEED_LINK = "https://natanedelsburg.github.io/axios-rss/feed.xml"
SITE_LINK = "https://www.axios.com/newsletters/axios-communicators"

# Atom namespace
ATOM_NS = "http://www.w3.org/2005/Atom"


def fetch_ktn_feed():
    """Fetch and parse the Kill the Newsletter Atom feed."""
    req = urllib.request.Request(KTN_FEED_URL, headers={"User-Agent": "axios-rss-archiver/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return ET.parse(response)


def parse_atom_entries(tree):
    """Extract entries from the Atom feed."""
    root = tree.getroot()
    entries = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        entry_id = entry.findtext(f"{{{ATOM_NS}}}id", "")
        title = entry.findtext(f"{{{ATOM_NS}}}title", "No title")
        published = entry.findtext(f"{{{ATOM_NS}}}published", "")
        updated = entry.findtext(f"{{{ATOM_NS}}}updated", "")
        content_el = entry.find(f"{{{ATOM_NS}}}content")
        content = content_el.text if content_el is not None and content_el.text else ""
        link_el = entry.find(f"{{{ATOM_NS}}}link[@rel='alternate']")
        link = link_el.get("href", "") if link_el is not None else ""

        # Skip confirmation and welcome/onboarding emails
        title_lower = title.lower()
        if ("confirm" in title_lower and "subscription" in title_lower) or \
           ("welcome to" in title_lower) or \
           ("action required" in title_lower):
            continue

        entries.append({
            "id": entry_id,
            "title": title,
            "published": published or updated,
            "content": content,
            "link": link,
        })
    return entries


def iso_to_rfc2822(iso_str):
    """Convert ISO 8601 date string to RFC 2822 format for RSS."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return format_datetime(dt)
    except (ValueError, AttributeError):
        return format_datetime(datetime.now(timezone.utc))


def load_existing_feed(filepath):
    """Load existing RSS feed and return set of known GUIDs and the item elements."""
    if not os.path.exists(filepath):
        return set(), []

    tree = ET.parse(filepath)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return set(), []

    known_ids = set()
    items = []
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        if guid_el is not None and guid_el.text:
            known_ids.add(guid_el.text)
        items.append(item)

    return known_ids, items


def build_rss_feed(existing_items, new_entries):
    """Build the full RSS 2.0 XML tree."""
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "description").text = FEED_DESCRIPTION
    ET.SubElement(channel, "link").text = SITE_LINK

    atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    atom_link.set("href", FEED_LINK)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
    ET.SubElement(channel, "generator").text = "axios-rss-archiver"

    # Add existing items first (preserves history)
    for item in existing_items:
        channel.append(item)

    # Add new entries
    for entry in new_entries:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = entry["title"]
        ET.SubElement(item, "link").text = entry["link"]
        ET.SubElement(item, "guid", isPermaLink="false").text = entry["id"]
        ET.SubElement(item, "pubDate").text = iso_to_rfc2822(entry["published"])
        ET.SubElement(item, "description").text = entry["content"]

    return rss


def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    # Load existing archive
    known_ids, existing_items = load_existing_feed(OUTPUT_FILE)
    print(f"Existing archive: {len(existing_items)} items, {len(known_ids)} known IDs")

    # Fetch new entries from KtN
    try:
        tree = fetch_ktn_feed()
    except Exception as e:
        print(f"Error fetching KtN feed: {e}")
        return

    atom_entries = parse_atom_entries(tree)
    print(f"Fetched {len(atom_entries)} entries from KtN (excluding confirmation emails)")

    # Deduplicate
    new_entries = [e for e in atom_entries if e["id"] not in known_ids]
    print(f"New entries to add: {len(new_entries)}")

    if not new_entries and existing_items:
        print("No new entries. Feed unchanged.")
        return

    # Build and write RSS feed
    rss = build_rss_feed(existing_items, new_entries)
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")

    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        tree.write(f, encoding="utf-8", xml_declaration=False)

    total = len(existing_items) + len(new_entries)
    print(f"Feed written to {OUTPUT_FILE} with {total} total items.")


if __name__ == "__main__":
    main()
