import os
from distutils.core import setup

from setuptools import find_packages

from modules import __version__

# User-friendly description from README.md
current_directory = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(current_directory, "README.md"), encoding="utf-8") as f:
        long_description = f.read()
except Exception:
    long_description = ""


setup(
    # Name of the package
    name="qbit_manage",
    # Packages to include into the distribution
    packages=find_packages("."),
    package_data={"": ["../*"]},
    include_package_data=True,
    # Start with a small number and increase it with
    # every change you make https://semver.org
    version=__version__,
    # Chose a license from here: https: //
    # help.github.com / articles / licensing - a -
    # repository. For example: MIT
    license="MIT",
    # Short description of your library
    description=(
        "This tool will help manage tedious tasks in qBittorrent and automate them. "
        "Tag, categorize, remove Orphaned data, remove unregistered torrents and much much more."
    ),
    # Long description of your library
    long_description=long_description,
    long_description_content_type="text/markdown",
    # Your name
    author="bobokun",
    # Your email
    author_email="",
    # Either the link to your github or to your website
    url="https://github.com/StuffAnThings",
    # Link from which the project can be downloaded
    download_url="https://github.com/StuffAnThings/qbit_manage",
)
