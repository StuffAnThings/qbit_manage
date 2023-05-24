import os

# Define an empty version_info tuple
__version_info__ = ()

# Get the path to the project directory
project_dir = os.path.dirname(os.path.abspath(__file__))

# Get the path to the VERSION file
version_file_path = os.path.join(project_dir, "..", "VERSION")

# Read the version from the file
with open(version_file_path) as f:
    version_str = f.read().strip()

# Get only the first 3 digits
version_str_split = version_str.rsplit("-", 1)[0]
# Convert the version string to a tuple of integers
__version_info__ = tuple(map(int, version_str_split.split(".")))

# Define the version string using the version_info tuple
__version__ = ".".join(str(i) for i in __version_info__)
