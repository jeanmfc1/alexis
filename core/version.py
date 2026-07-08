"""Single source of truth for the ALEXIS application version.

Bump the ONE line below to release a new version (semantic versioning:
MAJOR.MINOR.PATCH -- bump PATCH for fixes, MINOR for features, MAJOR for
breaking changes). It flows automatically to:
  * the API   -> /api/health, /api/info, /api/settings ("version")
  * the UI    -> the sidebar footer ("v<version>")
  * every build -> packaging/build.ps1 stamps it into the build folder name,
                   dist/builds.log, and a VERSION.txt inside the build.
"""

__version__ = "0.1.0"
