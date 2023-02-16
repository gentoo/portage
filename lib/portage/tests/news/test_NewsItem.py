# test_NewsItem.py -- Portage Unit Testing Functionality
# Copyright 2007-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.news import NewsItem
from portage.dbapi.virtual import fakedbapi
from tempfile import mkstemp

from dataclasses import dataclass
from string import Template
from typing import Optional

import textwrap

# The specification for news items is GLEP 42 ("Critical News Reporting"):
# https://www.gentoo.org/glep/glep-0042.html

# TODO(antarus) Make newsitem use a loader so we can load using a string instead of a tempfile


# TODO: port the real newsitem class to this?
@dataclass
class FakeNewsItem:
    title: str
    author: str
    content_type: str
    posted: str
    revision: int
    news_item_format: str
    content: str
    display_if_installed: Optional[list[str]] = None
    display_if_profile: Optional[list[str]] = None
    display_if_keyword: Optional[list[str]] = None

    item_template_header = Template(
        textwrap.dedent(
            """
        Title: ${title}
        Author: ${author}
        Content-Type: ${content_type}
        Posted: ${posted}
        Revision: ${revision}
        News-Item-Format: ${news_item_format}
        """
        )
    )

    def __post_init__(self):
        if not any(
            [self.display_if_installed, self.display_if_profile, self.display_if_keyword]
        ):
            raise ValueError(
                "At least one-of Display-If-Installed, Display-If-Profile, or Display-If-Arch must be set!"
            )

    def __str__(self) -> str:
        item = self.item_template_header.substitute(
            title=self.title,
            author=self.author,
            content_type=self.content_type,
            posted=self.posted,
            revision=self.revision,
            news_item_format=self.news_item_format,
        )

        for package in self.display_if_installed:
            item += f"Display-If-Installed: {package}\n"

        for profile in self.display_if_profile:
            item += f"Display-If-Profile: {profile}\n"

        for keyword in self.display_if_keyword:
            item += f"Display-If-Keyword: {keyword}\n"

        item += "\n"
        item += f"{self.content}"

        return item


class NewsItemTestCase(TestCase):
    # Default values for testing
    placeholders = {
        "title": "YourSQL Upgrades from 4.0 to 4.1",
        "author": "Ciaran McCreesh <ciaranm@gentoo.org>",
        "content_type": "Content-Type: text/plain",
        "posted": "01-Nov-2005",
        "revision": 1,
        "news_item_format": "1.0",
        "display_if_installed": [],
        "display_if_profile": [],
        "display_if_keyword": [],
        "content": textwrap.dedent(
            """
    YourSQL databases created using YourSQL version 4.0 are incompatible
    with YourSQL version 4.1 or later. There is no reliable way to
    automate the database format conversion, so action from the system
    administrator is required before an upgrade can take place.

    Please see the Gentoo YourSQL Upgrade Guide for instructions:

        http://www.gentoo.org/doc/en/yoursql-upgrading.xml

    Also see the official YourSQL documentation:

        http://dev.yoursql.com/doc/refman/4.1/en/upgrading-from-4-0.html

    After upgrading, you should also recompile any packages which link
    against YourSQL:

        revdep-rebuild --library=libyoursqlclient.so.12

    The revdep-rebuild tool is provided by app-portage/gentoolkit.
    """
        ),
    }

    def setUp(self) -> None:
        self.profile = "/var/db/repos/gentoo/profiles/default-linux/x86/2007.0/"
        self.keywords = "x86"
        # Consumers only use ARCH, so avoid portage.settings by using a dict
        self.settings = {"ARCH": "x86"}
        # Use fake/test dbapi to avoid slow tests
        self.vardb = fakedbapi(self.settings)

    def _createNewsItem(self, *kwargs) -> FakeNewsItem:
        # Use our placeholders unless overridden
        news_args = self.placeholders.copy()
        # Substitute in what we're given to allow for easily passing
        # just custom values.
        news_args.update(*kwargs)

        return FakeNewsItem(**news_args)

    def testBasicNewsItem(self):
        # Simple test with no filter fields (Display-If-*)
        try:
            item = self._processItem(str(self._createNewsItem()))
        finally:
            os.unlink(item.path)

    def testDisplayIfProfile(self):
        tmpItem = self._createNewsItem({"display_if_profile": [self.profile]})

        item = self._processItem(str(tmpItem))
        try:
            self.assertTrue(item.isValid())
            self.assertTrue(
                item.isRelevant(self.vardb, self.settings, self.profile),
                msg=f"Expected {tmpItem} to be relevant, but it was not!",
            )
        finally:
            os.unlink(item.path)

    def testDisplayIfInstalled(self):
        self.vardb.cpv_inject('sys-apps/portage-2.0', { 'SLOT' : "0" })
        tmpItem = self._createNewsItem({"display_if_installed": ["sys-apps/portage"]})

        try:
            item = self._processItem(str(tmpItem))
            self.assertTrue(item.isValid())
            self.assertTrue(
                item.isRelevant(self.vardb, self.settings, self.profile),
                msg=f"Expected {tmpItem} to be relevant, but it was not!",
            )
        finally:
            os.unlink(item.path)

        tmpItem = self._createNewsItem({"display_if_installed": ["sys-apps/i-do-not-exist"]})

        try:
            item = self._processItem(str(tmpItem))
            self.assertTrue(item.isValid())
            self.assertFalse(
                item.isRelevant(self.vardb, self.settings, self.profile),
                msg=f"Expected {tmpItem} to be irrelevant, but it was relevant!",
            )
        finally:
            os.unlink(item.path)

    def testDisplayIfKeyword(self):
        tmpItem = self._createNewsItem({"display_if_keyword": [self.keywords]})

        try:
            item = self._processItem(str(tmpItem))
            self.assertTrue(item.isValid())
            self.assertTrue(
                item.isRelevant(self.vardb, self.settings, self.profile),
                msg=f"Expected {tmpItem} to be relevant, but it was not!",
            )
        finally:
            os.unlink(item.path)

    def _processItem(self, item) -> NewsItem:
        filename = None
        fd, filename = mkstemp()
        f = os.fdopen(fd, "w")
        f.write(item)
        f.close()
        try:
            return NewsItem(filename, 0)
        except TypeError:
            self.fail(f"Error while processing news item {filename}")
