#!/usr/bin/env python3

import argparse
import bs4
import bs4.element
import json
import requests
import ruamel.yaml
import sys

# Treat these as constants
_base = "https://archiveofourown.org"
_group_path = "/media/{}/fandoms"
_group_names = {
    "anime": "Anime%20*a*%20Manga",
    "books": "Books%20*a*%20Literature",
    "cartoons": "Cartoons%20*a*%20Comics%20*a*%20Graphic%20Novels",
    "celebrities": "Celebrities%20*a*%20Real People",
    "movies": "Movies",
    "music": "Music%20*a*%20Bands",
    "other": "Other%20Media",
    "theater": "Theater",
    "tv": "TV%20Shows",
    "videogames": "Video%20Games",
}


class Fetcher(object):
    def __init__(self, baseurl=_base, media_path=_group_path):
        self._base = baseurl
        self._media_path = media_path
        self.verbosity = 1

    def vprint(self, msg, verbosity=1):
        if self.verbosity >= verbosity:
            print(msg)

    def _fetch_fandoms(self, url):
        self.vprint("Fetching fandoms from {}".format(url), 1)
        resp = requests.get(url)
        resp.raise_for_status()
        soup = bs4.BeautifulSoup(resp.text, 'html.parser')
        listitems = soup.find_all(class_="tags index group")
        items = list()
        for entry in listitems:
            items.extend(self._parse_group(entry))
        self.vprint("Fetched {} fandoms from {}".format(len(items), url), 2)
        return items

    def _parse_group(self, group):
        items = list()
        for child in group.children:
            # Skip anything that's not a tagged element, and isn't a list item
            if type(child) is not bs4.element.Tag or child.name != 'li':
                continue

            # Parse the child into a name, count, and URL
            path = self._base + child.find('a').attrs['href']
            text = child.text.strip()
            parts = text.rsplit(maxsplit=1)
            # (name, count, url)
            items.append((parts[0].strip(), int(parts[1].strip()[1:-1]), path))
        return items

    def fetch_all(self, groups, mincount=0):
        items = list()
        for group in groups:
            url = self._base + self._media_path.format(group)
            fandoms = self._fetch_fandoms(url)
            expected = len(items) + len(fandoms)
            for f in fandoms:
                if f not in items:
                    items.append(f)
            actual = len(items)
            if expected != actual:
                self.vprint("Merging lists resulted in dropping {} duplicates".format(expected-actual), 2)

        expected = len(items)
        # Sort by values
        results = sorted(filter(lambda x: x[1] >= mincount, items), key=lambda x: x[1], reverse=True)
        actual = len(results)
        if expected != actual:
            self.vprint("Filtered {} fandoms out for having too few works".format(expected - actual), 2)
        return results


def convert_json(fandoms):
    return [{"count": f[1], "name": f[0], "url": f[2]} for f in fandoms]


def output_text(fandoms, fp):
    for f in fandoms:
        fp.write("{} {} - {}\n".format(f[0], f[1], f[2]))


def output_table(fandoms, fp):
    headers = ("count", "name", "URL")
    sizes = [len(s) for s in headers]
    for f in fandoms:
        sizes[0] = max(sizes[0], len(str(f[1])))
        sizes[1] = max(sizes[1], len(str(f[0])))
        sizes[2] = max(sizes[2], len(str(f[2])))

    header = headers[0].ljust(sizes[0])
    header += " | " + headers[1].ljust(sizes[1])
    header += " | " + headers[2] + "\n"
    fp.write(header)
    fp.write("-"*sizes[0]+"-|-"+"-"*sizes[1]+"-|-"+"-"*sizes[2]+"\n")
    for f in fandoms:
        line = str(f[1]).ljust(sizes[0])
        line += " | " + f[0].ljust(sizes[1])
        line += " | " + f[2] + "\n"
        fp.write(line)


def output_json(fandoms, fp):
    json.dump(convert_json(fandoms), fp, indent=2)


def output_json_compact(fandoms, fp):
    json.dump(convert_json(fandoms), fp, indent=None)


def output_yaml(fandoms, fp):
    ruamel.yaml.dump(convert_json(fandoms), stream=fp, default_flow_style=False)


formatters = {
    "text": output_text,
    "table": output_table,
    "json": output_json,
    "json-compact": output_json_compact,
    "yaml": output_yaml,
}


def parse_args(args):
    parser = argparse.ArgumentParser(description='Scrape AO3 for fandom lists')
    parser.add_argument(
        '--output', '-o',
        help="The format to output the results of the scrape in",
        default='text', type=str, choices=formatters.keys()
    )
    parser.add_argument(
        '--category', '-c',
        help="The set of categories to scrape",
        choices=_group_names.keys(), action='append'
    )
    parser.add_argument(
        '--verbose', '-v',
        help="Enable verbose output",
        action='store_const', const=2, dest='verbosity', default=1
    )
    parser.add_argument(
        '--quiet', '-q',
        help="Disable all output",
        action='store_const', const=0, dest='verbosity'
    )
    parser.add_argument(
        '--min-works', '-m',
        help="A minimum number of works to enforce on the resulting list",
        type=int, default=0
    )
    parser.add_argument(
        '--file', '-f',
        help="The file to output to - if not specified, the results are written to stdout",
        type=str
    )

    return parser.parse_args(args)


def main(args):
    flags = parse_args(args)
    f = Fetcher()
    f.verbosity = flags.verbosity

    categories = flags.category
    if categories is None:
        categories = _group_names.keys()

    groups = [_group_names[category] for category in categories]
    fandoms = None
    try:
        fandoms = f.fetch_all(groups, flags.min_works)
    except Exception as e:
        print("Failed to fetch fandoms: {}".format(e))
        return 1

    fp = sys.stdout
    if flags.file is not None:
        try:
            fp = open(flags.file, "w")
        except Exception as e:
            print("Could not open file {} for writing:\n{}".format(flags.file, e))
            return 1

    formatters[flags.output](fandoms, fp)
    if fp is not sys.stdout:
        fp.close()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
