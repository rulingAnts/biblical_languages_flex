"""
flex_project.py — Lightweight FLEx LCM project wrapper
=======================================================
Derived from FLExProject in the FLExTools project by Richard Louw.
  Source: https://github.com/rmlockwood/FLExTools
  License: GNU Lesser General Public License v3 (LGPL-3.0)
  Original copyright: Richard Louw / SIL International contributors

Modifications from the original:
  - Stripped to only the functionality needed by this application
  - Removed FLExTools UI/report dependencies
  - Added explicit FLEx installation path detection via Windows registry
  - Raises plain Python exceptions instead of returning error codes

UPSTREAM TRACKING
  Derived from FLExTools commit: (record hash when you copy from upstream)
  FLExTools version at time of copy: (record version)
  To update: compare flex_project.py against FLExTools/flextoolslib/FLExProject.py
  and selectively merge fixes, being careful to preserve our modifications above.

REQUIREMENTS
  - FLEx (FieldWorks Language Explorer) must be installed
  - Python.NET (pythonnet) must be installed: pip install pythonnet
  - Windows only (FLEx is Windows-only)
"""

import os
import sys
import winreg
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locate FLEx installation and load SIL.LCModel DLLs
# ---------------------------------------------------------------------------

def _find_flex_dir():
    """
    Return the FLEx installation directory by reading the Windows registry.
    Raises RuntimeError if FLEx is not found.
    """
    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\SIL\FieldWorks\9",
         "RootCodeDir"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\SIL\FieldWorks\9",
         "RootCodeDir"),
    ]
    for hive, key_path, value_name in registry_paths:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                path, _ = winreg.QueryValueEx(key, value_name)
                if path and os.path.isdir(path):
                    log.info('FLEx installation found at: %s', path)
                    return path
        except OSError:
            continue
    raise RuntimeError(
        "FieldWorks Language Explorer does not appear to be installed.\n"
        "Please install FLEx from https://software.sil.org/fieldworks/ and try again."
    )


def _load_lcm(flex_dir):
    """
    Configure Python.NET to load SIL.LCModel DLLs from the FLEx directory
    and import the core LCM namespaces.

    Must be called once before any SIL.LCModel imports elsewhere.
    """
    import clr  # pythonnet

    # Add the FLEx directory so .NET can resolve assembly dependencies
    sys.path.insert(0, flex_dir)
    clr.AddReference(os.path.join(flex_dir, 'SIL.LCModel.dll'))
    clr.AddReference(os.path.join(flex_dir, 'SIL.LCModel.Core.dll'))
    clr.AddReference(os.path.join(flex_dir, 'SIL.LCModel.Infrastructure.dll'))

    log.info('SIL.LCModel DLLs loaded from %s', flex_dir)


# ---------------------------------------------------------------------------
# FLExProject — open/close a FLEx project and expose the LCM cache
# ---------------------------------------------------------------------------

class FLExProject:
    """
    Opens a FLEx .fwdata project file and exposes the LCM cache.

    Usage:
        project = FLExProject(r"C:\\path\\to\\MyProject\\MyProject.fwdata")
        try:
            # use project.cache, project.lp, project.ObjectsIn(...)
        finally:
            project.close()

    Or as a context manager:
        with FLExProject(path) as project:
            ...

    FLEx MUST be closed before opening the project here — LCM uses
    exclusive file locking.
    """

    def __init__(self, fwdata_path):
        self._fwdata_path = fwdata_path
        self._cache = None
        self._flex_dir = _find_flex_dir()
        _load_lcm(self._flex_dir)
        self._open()

    # -- internal ------------------------------------------------------------

    def _open(self):
        from SIL.LCModel import (
            LcmCache,
            BackendProviderType,
        )
        from SIL.LCModel.Infrastructure import SimpleProjectId

        project_id = SimpleProjectId(
            BackendProviderType.kXMLWithMemoryOnlyWsMgr,
            self._fwdata_path,
        )

        # TODO: supply a real IThreadedProgress if progress reporting is needed
        self._cache = LcmCache.CreateCacheFromLocalProjectFiles(
            project_id,
            None,   # IThreadedProgress
            None,   # IProjectIdentifier override
        )
        log.info('LCM project opened: %s', self._fwdata_path)

    def close(self):
        if self._cache is not None:
            self._cache.Dispose()
            self._cache = None
            log.info('LCM project closed')

    # -- context manager -----------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -- convenience properties (mirrors FLExTools FLExProject API) ----------

    @property
    def project(self):
        """The raw LCM cache object (LcmCache). Equivalent to FLExTools project.project."""
        return self._cache

    @property
    def lp(self):
        """The LangProject object. Equivalent to FLExTools project.lp."""
        return self._cache.LangProject

    def ObjectsIn(self, repository_type):
        """
        Iterate all objects of the given repository type.
        Equivalent to FLExTools project.ObjectsIn(IXxxRepository).

        Example:
            from SIL.LCModel import ISegmentRepository
            for seg in project.ObjectsIn(ISegmentRepository):
                ...
        """
        repo = self._cache.ServiceLocator.GetService(repository_type)
        return repo.AllInstances()
