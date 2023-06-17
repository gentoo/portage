# test_NewsItem.py -- Portage Unit Testing Functionality
# Copyright 2007-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.news import NewsItem, NewsManager
from portage.dbapi.virtual import fakedbapi

from dataclasses import dataclass
from string import Template
from typing import Optional, List
from unittest.mock import MagicMock, mock_open, patch

import textwrap

# The specification for news items is GLEP 42 ("Critical News Reporting"):
# https://www.gentoo.org/glep/glep-0042.html


@dataclass
class FakeNewsItem(NewsItem):
    title: str
    author: str
    content_type: str
    posted: str
    revision: int
    news_item_format: str
    content: str
    display_if_installed: Optional[List[str]] = None
    display_if_profile: Optional[List[str]] = None
    display_if_keyword: Optional[List[str]] = None

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
        super().__init__(path="mocked_news", name=self.title)

    def isValid(self):
        with patch("builtins.open", mock_open(read_data=str(self))):
            return super().isValid()

    # TODO: Migrate __str__ to NewsItem? NewsItem doesn't actually parse
    # all fields right now though.
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

        item += f"\n{self.content}"

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

        https://gentoo.org/doc/en/yoursql-upgrading.xml

    Also see the official YourSQL documentation:

        https://dev.example.com/doc/refman/4.1/en/upgrading-from-4-0.html

    After upgrading, you should also recompile any packages which link
    against YourSQL:

        revdep-rebuild --library=libyoursqlclient.so.12

    The revdep-rebuild tool is provided by app-portage/gentoolkit.
    """
        ),
    }

    def setUp(self) -> None:
        self.profile_base = "/var/db/repos/gentoo/profiles/default-linux"
        self.profile = f"{self.profile_base}/x86/2007.0/"
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

    def _checkAndCreateNewsItem(
        self, news_args: dict, relevant: bool = True, reason: str = ""
    ) -> FakeNewsItem:
        return self._checkNewsItem(self._createNewsItem(news_args), relevant, reason)

    def _checkNewsItem(self, item: NewsItem, relevant: bool = True, reason: str = ""):
        self.assertTrue(item.isValid())

        if relevant:
            self.assertTrue(
                item.isRelevant(self.vardb, self.settings, self.profile),
                msg=f"Expected {item} to be relevant, but it was not!",
            )
        else:
            self.assertFalse(
                item.isRelevant(self.vardb, self.settings, self.profile),
                msg=f"Expected {item} to be irrelevant, but it was relevant!",
            )

    def testNewsManager(self):
        vardb = MagicMock()
        portdb = MagicMock()
        portdb.repositories.mainRepoLocation = MagicMock(return_value="/tmp/repo")
        portdb.settings.profile_path = "/tmp/repo/profiles/arch/amd64"

        news_manager = NewsManager(portdb, vardb, portdb.portdir, portdb.portdir)
        self.assertEqual(news_manager._profile_path, "arch/amd64")
        self.assertNotEqual(news_manager._profile_path, "tmp/repo/profiles/arch/amd64")

    def testBasicNewsItem(self):
        # Simple test with no filter fields (Display-If-*)
        item = self._createNewsItem()
        self.assertTrue(item.isValid())
        self.assertTrue(item.isRelevant(self.vardb, self.settings, self.profile))

        # Does an invalid item fail? ("a" is not a valid package name)
        item = self._createNewsItem({"display_if_installed": "a"})
        self.assertFalse(item.isValid())

    def testDisplayIfProfile(self):
        # We repeat all of these with the full profile path (including repo)
        # and a relative path, as we've had issues there before.
        # Note that we can't use _checkNewsItem() here as we override the
        # profile value passed to isRelevant.
        for profile_prefix in ("", self.profile_base):
            # First, just check the simple case of one profile matching ours.
            item = self._createNewsItem(
                {"display_if_profile": [profile_prefix + self.profile]}
            )
            self.assertTrue(item.isValid())
            self.assertTrue(
                item.isRelevant(
                    self.vardb, self.settings, profile_prefix + self.profile
                ),
                msg=f"Expected {item} to be relevant, but it was not!",
            )

            # Test the negative case: what if the only profile listed
            # does *not* match ours?
            item = self._createNewsItem(
                {"display_if_profile": [profile_prefix + "profiles/i-do-not-exist"]}
            )
            self.assertTrue(item.isValid())
            self.assertFalse(
                item.isRelevant(
                    self.vardb, self.settings, profile_prefix + self.profile
                ),
                msg=f"Expected {item} to be irrelevant, but it was relevant!",
            )

            # What if several profiles are listed and we match one of them?
            item = self._createNewsItem(
                {
                    "display_if_profile": [
                        profile_prefix + self.profile,
                        profile_prefix + f"{self.profile_base}/amd64/2023.0",
                    ]
                }
            )
            self.assertTrue(item.isValid())
            self.assertTrue(
                item.isRelevant(
                    self.vardb, self.settings, profile_prefix + self.profile
                ),
                msg=f"Expected {item} to be relevant, but it was not!",
            )

            # What if several profiles are listed and we match none of them?
            item = self._createNewsItem(
                {
                    "display_if_profile": [
                        profile_prefix + f"{self.profile_base}/x86/2023.0",
                        profile_prefix + f"{self.profile_base}/amd64/2023.0",
                    ]
                }
            )
            self.assertTrue(item.isValid())
            self.assertFalse(
                item.isRelevant(
                    self.vardb, self.settings, profile_prefix + self.profile
                ),
                msg=f"Expected {item} to be irrelevant, but it was relevant!",
            )

    def testDisplayIfInstalled(self):
        self.vardb.cpv_inject("sys-apps/portage-2.0", {"SLOT": "0"})

        self._checkAndCreateNewsItem({"display_if_installed": ["sys-apps/portage"]})

        # Test the negative case: a single Display-If-Installed listing
        # a package we don't have.
        self._checkAndCreateNewsItem(
            {"display_if_installed": ["sys-apps/i-do-not-exist"]}, False
        )

        # What about several packages and we have none of them installed?
        self._checkAndCreateNewsItem(
            {
                "display_if_installed": [
                    "dev-util/pkgcheck",
                    "dev-util/pkgdev",
                    "sys-apps/pkgcore",
                ]
            },
            False,
        )

        # What about several packages and we have one of them installed?
        self.vardb.cpv_inject("net-misc/openssh-9.2_p1", {"SLOT": "0"})
        self._checkAndCreateNewsItem(
            {
                "display_if_installed": [
                    "net-misc/openssh",
                    "net-misc/dropbear",
                ]
            }
        )

        # What about several packages and we have all of them installed?
        # Note: we already have openssh added from the above test
        self.vardb.cpv_inject("net-misc/dropbear-2022.83", {"SLOT": "0"})
        self._checkAndCreateNewsItem(
            {
                "display_if_installed": [
                    "net-misc/openssh",
                    "net-misc/dropbear",
                ]
            }
        )

        # What if we have a newer version of the listed package which
        # shouldn't match the constraint?
        self._checkAndCreateNewsItem(
            {
                "display_if_installed": [
                    "<net-misc/openssh-9.2_p1",
                ]
            },
            False,
        )

        # What if we have a newer version of the listed package which
        # should match the constraint?
        self._checkAndCreateNewsItem(
            {
                "display_if_installed": [
                    ">=net-misc/openssh-9.2_p1",
                ]
            }
        )

        # What if the item lists multiple packages and we have one of
        # them installed, but not all?
        # (Note that openssh is already "installed" by this point because
        # of a previous test.)
        self._checkAndCreateNewsItem(
            {
                "display_if_installed": [
                    ">=net-misc/openssh-9.2_p1",
                    "<net-misc/openssh-9.2_p1",
                ]
            }
        )

    def testDisplayIfKeyword(self):
        self._checkAndCreateNewsItem({"display_if_keyword": [self.keywords]})

        # Test the negative case: a keyword we don't have set.
        self._checkAndCreateNewsItem({"display_if_keyword": ["fake-keyword"]}, False)

        # What if several keywords are listed and we match one of them?
        self._checkAndCreateNewsItem(
            {"display_if_keyword": [self.keywords, "amd64", "~hppa"]}
        )

        # What if several keywords are listed and we match none of them?
        self._checkAndCreateNewsItem({"display_if_keyword": ["amd64", "~hppa"]}, False)

        # What if the ~keyword (testing) keyword is listed but we're keyword (stable)?
        self._checkAndCreateNewsItem(
            {
                "display_if_keyword": [
                    f"~{self.keywords}",
                ]
            },
            False,
        )

        # What if the stable keyword is listed but we're ~keyword (testing)?
        self._checkAndCreateNewsItem(
            {
                "display_if_keyword": [
                    f"{self.keywords}",
                ]
            }
        )

    def testMultipleRestrictions(self):
        # GLEP 42 specifies an algorithm for how combining restrictions
        # should work. See https://www.gentoo.org/glep/glep-0042.html#news-item-headers.
        # Different types of Display-If-* are ANDed, not ORed.

        # What if there's a Display-If-Keyword that matches and a
        # Display-If-Installed which does too?
        self.vardb.cpv_inject("sys-apps/portage-2.0", {"SLOT": "0"})
        self._checkAndCreateNewsItem(
            {
                "display_if_keyword": [self.keywords],
                "display_if_installed": ["sys-apps/portage"],
            }
        )

        # What if there's a Display-If-Keyword that matches and a
        # Display-If-Installed which doesn't?
        self._checkAndCreateNewsItem(
            {
                "display_if_keyword": [self.keywords],
                "display_if_installed": ["sys-apps/i-do-not-exist"],
            },
            False,
        )

        # What if there's a Display-If-{Installed,Keyword,Profile} and
        # they all match?
        # (Note that sys-apps/portage is already "installed" by this point
        # because of the above test.)
        self._checkAndCreateNewsItem(
            {
                "display_if_keyword": [self.keywords],
                "display_if_installed": ["sys-apps/portage"],
                "display_if_profile": [self.profile],
            }
        )

        # What if there's a Display-If-{Installed,Keyword,Profile} and
        # none of them match?
        # (Note that sys-apps/portage is already "installed" by this point
        # because of the above test.)
        self._checkAndCreateNewsItem(
            {
                "display_if_keyword": ["i-do-not-exist"],
                "display_if_installed": ["sys-apps/i-do-not-exist"],
                "display_if_profile": [self.profile_base + "/i-do-not-exist"],
            },
            False,
        )
