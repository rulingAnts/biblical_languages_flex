; FLEx Gloss Splitter — FLExTools Module Installer
; Inno Setup 6  (https://jrsoftware.org/isinfo.php)
;
; What this installer does:
;   1. Verifies FLEx is installed — offers to open the download page if not,
;      then aborts (FLEx must be installed before we can proceed).
;   2. Verifies Python (py.exe) is available — offers to download and run the
;      official Python installer if not.  Aborts cleanly (before touching any
;      files) if Python is still unavailable afterward.
;   3. Installs FLExTools if missing: copies bundled loose files to
;      %LOCALAPPDATA%\FLExTools\ and creates a Start Menu shortcut, then runs:
;        py -m pip install --upgrade flextoolslib
;   4. Copies Split_Slash_Glosses.py into the FLExTools Modules folder.
;   5. Finish page explains how to use the module via FLExTools.
;   6. Uninstaller removes only Split_Slash_Glosses.py and itself.
;      FLExTools, Python, and FLEx are left in place with instructions on
;      how to remove them separately if desired.
;
; Note: FLExTools is a standalone application — modules are run from within
;   FLExTools, not from within FLEx itself.  Open FLEx first (with a project
;   loaded), then launch FLExTools from the Start Menu.
;
; License note: FLExTools is distributed under LGPL 2.1 or later.
;   Its LICENSE file is included in this installer as required.
;
; Build: called by the GitHub Actions release-installer.yml workflow,
;   which passes /DFLEXTOOLS_VERSION=X.Y.Z after downloading FlexTools.zip.

; -------------------------------------------------------------------------
; Defines — FLEXTOOLS_VERSION is passed by the build system at compile time
; -------------------------------------------------------------------------
#ifndef FLEXTOOLS_VERSION
  #define FLEXTOOLS_VERSION "0.0.0"
#endif
#define AppName        "FLEx Gloss Splitter (FLExTools Module)"
#define AppShortName   "FLExGlossSplitter"
#define AppVersion     "1.0"
#define AppPublisher   "Biblical Languages FLEx Tools"
#define ModuleFile     "Split_Slash_Glosses.py"
#define AppId          "{{A3F2C1D4-8E5B-4A9C-B7D6-2E3F4A5B6C7D}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppVerName={#AppName} {#AppVersion}

DefaultDirName={localappdata}\{#AppShortName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
DisableProgramGroupPage=yes
DisableStartupPrompt=yes

OutputDir=Output
OutputBaseFilename=FLExGlossSplitterModuleSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes

UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; FLExTools application files (extracted from the release zip at CI build time).
; Copied only when FLExTools is not already installed (Check: DoInstallFLExTools).
Source: "FlexToolsFiles\*"; DestDir: "{localappdata}\FLExTools"; \
    Flags: recursesubdirs ignoreversion; Check: DoInstallFLExTools

; FLExTools LICENSE — required by LGPL 2.1 for redistribution
Source: "FlexTools_LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; Our module — copied to the FLExTools Modules folder
Source: "..\tools\{#ModuleFile}"; DestDir: "{code:GetModulesDir}"; \
    Flags: ignoreversion

[Icons]
; Start Menu shortcut for FLExTools — created when we install FLExTools.
; uninsneveruninstall: FLExTools itself is not uninstalled by us, so leave
; the shortcut in place when our module is removed.
Name: "{userprograms}\FLExTools\FLExTools"; \
    Filename: "{win}\py.exe"; \
    Parameters: """{localappdata}\FLExTools\FlexTools.py"""; \
    WorkingDir: "{localappdata}\FLExTools"; \
    Comment: "Run FLExTools — utilities for FieldWorks Language Explorer"; \
    Flags: uninsneveruninstall; Check: DoInstallFLExTools

[Registry]
; Remember the Modules dir so future upgrades pre-fill correctly
Root: HKCU; \
    Subkey: "Software\{#AppShortName}"; \
    ValueType: string; ValueName: "ModulesDir"; \
    ValueData: "{code:GetModulesDir}"; \
    Flags: uninsdeletekey

[UninstallDelete]
; Remove only our module file — FLExTools itself is intentionally left alone
Type: files; Name: "{code:GetModulesDir}\{#ModuleFile}"

[Run]
; Offer to launch FLExTools immediately after install
Filename: "{win}\py.exe"; \
    Parameters: """{localappdata}\FLExTools\FlexTools.py"""; \
    WorkingDir: "{localappdata}\FLExTools"; \
    Description: "Launch FLExTools now"; \
    Flags: nowait postinstall skipifsilent unchecked

[Messages]
FinishedLabel=The Split Slash Glosses module has been installed.%n%nTo use it: close FLEx, launch FLExTools from the Start Menu, select your project, and run Split Slash Glosses. Then close FLExTools and reopen FLEx to see the changes.

; -------------------------------------------------------------------------
; Code
; -------------------------------------------------------------------------
[Code]

const
  BundledFLExToolsVersion = '{#FLEXTOOLS_VERSION}';
  FLExDownloadURL    = 'https://software.sil.org/fieldworks/download/';
  // Update this URL when a new Python stable release ships
  PythonInstallerURL = 'https://www.python.org/ftp/python/3.13.3/python-3.13.3-amd64.exe';

{ BoolToStr is not a built-in in Inno Setup Pascal }
function BoolStr(B: Boolean): String;
begin
  if B then Result := 'True' else Result := 'False';
end;

var
  ModulesDirPage : TInputDirWizardPage;
  ModulesDir     : String;
  NeedsFLExTools : Boolean;  { True if FLExTools app files should be installed }
  NeedsPython    : Boolean;  { True if py.exe was not found at startup }
  PyExePath      : String;   { Resolved path to py.exe, set by PrepareToInstall }


{ -----------------------------------------------------------------------
  FLEx detection
  ----------------------------------------------------------------------- }

{ Scan SilDir for any FieldWorks* subdirectory; returns first match or '' }
function ScanForFLExUnder(SilDir: String): String;
var
  FindRec: TFindRec;
begin
  Result := '';
  if not DirExists(SilDir) then Exit;
  Log('Scanning for FLEx under: ' + SilDir);
  if FindFirst(SilDir + 'FieldWorks*', FindRec) then begin
    try
      repeat
        if (FindRec.Attributes and $10) <> 0 then begin   { FILE_ATTRIBUTE_DIRECTORY }
          Log('FLEx candidate dir: ' + FindRec.Name);
          Result := SilDir + FindRec.Name;
          Exit;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function GetFLExInstallDir(): String;
var
  PF64: String;
begin
  Result := '';

  // FLEx 9.x is 64-bit. On a 32-bit Inno Setup process the pf constant points
  // to "Program Files (x86)", so use ProgramW6432 — the env var that always
  // returns the native 64-bit Program Files path, even from a 32-bit process.
  PF64 := GetEnv('ProgramW6432');
  if PF64 <> '' then begin
    Result := ScanForFLExUnder(PF64 + '\SIL\');
    if Result <> '' then begin Log('FLEx found under ProgramW6432: ' + Result); Exit; end;
  end;

  { Fallbacks for 32-bit Windows or unusual install locations }
  Result := ScanForFLExUnder(ExpandConstant('{pf}\SIL\'));
  if Result <> '' then begin Log('FLEx found under {pf}: ' + Result); Exit; end;

  Result := ScanForFLExUnder(ExpandConstant('{pf32}\SIL\'));
  if Result <> '' then begin Log('FLEx found under {pf32}: ' + Result); Exit; end;

  Log('FLEx install dir not found');
end;

function FLExIsInstalled(): Boolean;
begin
  Result := GetFLExInstallDir() <> '';
  Log('FLEx installed: ' + BoolStr(Result));
end;


{ -----------------------------------------------------------------------
  FLExTools detection — filesystem only, no cmd.exe or Python required
  ----------------------------------------------------------------------- }

function FLExToolsIsInstalled(): Boolean;
var
  Marker: String;
begin
  // scripts\requirements.txt is part of the FLExTools app files bundle;
  // its presence means the app files have been installed.
  Marker := ExpandConstant('{localappdata}\FLExTools\scripts\requirements.txt');
  Result := FileExists(Marker);
  Log('FLExTools app files installed: ' + BoolStr(Result) + '  (marker: ' + Marker + ')');
end;

{ Used as Check: in the [Files] and [Icons] sections }
function DoInstallFLExTools(): Boolean;
begin
  Result := NeedsFLExTools;
end;


{ -----------------------------------------------------------------------
  Python (py.exe) detection
  ----------------------------------------------------------------------- }

function FindPyExe(): String;
var
  Candidate: String;
begin
  Result := '';

  // System-wide Python Launcher — installed to Windows dir for all-users installs
  Candidate := ExpandConstant('{win}\py.exe');
  if FileExists(Candidate) then begin Log('py.exe found: ' + Candidate); Result := Candidate; Exit; end;

  // Per-user Python Launcher location (Python 3.x per-user install)
  Candidate := ExpandConstant('{localappdata}\Programs\Python\Launcher\py.exe');
  if FileExists(Candidate) then begin Log('py.exe found: ' + Candidate); Result := Candidate; Exit; end;

  Log('py.exe not found');
end;


{ -----------------------------------------------------------------------
  File download via PowerShell Net.WebClient (hidden, no console window)
  ----------------------------------------------------------------------- }

function DownloadFile(URL: String; DestPath: String): Boolean;
var
  PSCmd: String;
  ResultCode: Integer;
begin
  Result := False;
  // Use PowerShell's Net.WebClient so no console window appears.
  // -NonInteractive -NoProfile keep startup fast and silent.
  PSCmd := '-NonInteractive -NoProfile -Command '
    + '"(New-Object Net.WebClient).DownloadFile(''' + URL + ''', ''' + DestPath + ''')"';
  Log('Downloading: ' + URL + ' -> ' + DestPath);
  if not Exec('powershell.exe', PSCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    Log('powershell.exe could not be launched for download');
    Exit;
  end;
  if ResultCode <> 0 then begin
    Log('Download failed with exit code: ' + IntToStr(ResultCode));
    Exit;
  end;
  Result := FileExists(DestPath);
  Log('Download success: ' + BoolStr(Result));
end;


{ -----------------------------------------------------------------------
  FLExTools Modules directory detection
  ----------------------------------------------------------------------- }

function DetectModulesDir(): String;
var
  Candidate: String;
begin
  Result := '';
  { Check registry first (written by a previous run of our installer) }
  if RegQueryStringValue(HKCU,
    'Software\{#AppShortName}', 'ModulesDir', Candidate) then
    if DirExists(Candidate) then
      begin Result := Candidate; Log('Modules dir from registry: ' + Candidate); Exit; end;

  { Common FLExTools install locations }
  Candidate := ExpandConstant('{localappdata}\FLExTools\Modules');
  if DirExists(Candidate) then begin Log('Detected: ' + Candidate); Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{localappdata}\Programs\FLExTools\Modules');
  if DirExists(Candidate) then begin Log('Detected: ' + Candidate); Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{pf}\FLExTools\Modules');
  if DirExists(Candidate) then begin Log('Detected: ' + Candidate); Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{pf32}\FLExTools\Modules');
  if DirExists(Candidate) then begin Log('Detected: ' + Candidate); Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{pf}\SIL\FieldWorks\FLExTools\Modules');
  if DirExists(Candidate) then begin Log('Detected: ' + Candidate); Result := Candidate; Exit; end;
  Candidate := ExpandConstant('{pf32}\SIL\FieldWorks\FLExTools\Modules');
  if DirExists(Candidate) then begin Log('Detected: ' + Candidate); Result := Candidate; Exit; end;

  Log('FLExTools Modules dir not detected');
end;


{ -----------------------------------------------------------------------
  Wizard lifecycle
  ----------------------------------------------------------------------- }

function InitializeSetup(): Boolean;
var
  Answer: Integer;
begin
  Result := True;

  // ---- FLEx check ----
  if not FLExIsInstalled() then begin
    Answer := MsgBox(
      'FieldWorks Language Explorer (FLEx) must be installed before running this setup.'
      + #13#10#13#10
      + 'Would you like to open the FLEx download page in your browser?'
      + #13#10
      + '(Setup will exit — re-run this installer after FLEx is installed.)',
      mbConfirmation, MB_YESNO);
    if Answer = IDYES then
      ShellExec('open', FLExDownloadURL, '', '', SW_SHOWNORMAL, ewNoWait, Answer);
    Result := False;
    Exit;
  end;

  // ---- Python check: ask now, actually install in PrepareToInstall ----
  NeedsPython := FindPyExe() = '';
  if NeedsPython then begin
    Answer := MsgBox(
      'Python is required but was not found on this computer.'
      + #13#10#13#10
      + 'Click Yes to download and run the Python installer automatically.'
      + #13#10
      + 'Click No to cancel — install Python manually from https://python.org,'
      + #13#10
      + 'then re-run this setup.',
      mbConfirmation, MB_YESNO);
    if Answer = IDNO then begin
      Result := False;
      Exit;
    end;
    // Download + install happens in PrepareToInstall(), before any files are touched
  end;

  // ---- FLExTools check ----
  NeedsFLExTools := not FLExToolsIsInstalled();
  if NeedsFLExTools then
    Log('FLExTools not found — will install bundled version ' + BundledFLExToolsVersion)
  else
    Log('FLExTools already installed — skipping');
end;

{ Called after wizard pages but BEFORE any files are installed.
  A non-empty return string aborts the installation cleanly. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  TempInstaller: String;
  ResultCode: Integer;
begin
  Result := '';  { empty = proceed }

  if not NeedsPython then begin
    PyExePath := FindPyExe();
    Exit;
  end;

  // ---- Download Python installer ----
  WizardForm.StatusLabel.Caption := 'Downloading Python installer...';
  TempInstaller := ExpandConstant('{tmp}\python_installer.exe');

  if not DownloadFile(PythonInstallerURL, TempInstaller) then begin
    Result := 'Could not download the Python installer.'
      + #13#10
      + 'Please install Python manually from https://python.org, then re-run this setup.';
    Exit;
  end;

  // ---- Run Python installer interactively ----
  WizardForm.StatusLabel.Caption := 'Running Python installer — please complete it to continue...';
  Log('Launching Python installer: ' + TempInstaller);

  if not Exec(TempInstaller, '', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then begin
    Result := 'Could not launch the Python installer.'
      + #13#10
      + 'Please install Python manually from https://python.org, then re-run this setup.';
    Exit;
  end;

  if ResultCode <> 0 then begin
    Log('Python installer exited with code: ' + IntToStr(ResultCode));
    Result := 'The Python installer did not complete successfully (exit code: '
      + IntToStr(ResultCode) + ').'
      + #13#10
      + 'Please install Python manually from https://python.org, then re-run this setup.';
    Exit;
  end;

  // ---- Verify py.exe is now available ----
  PyExePath := FindPyExe();
  if PyExePath = '' then begin
    Result := 'Python was installed but the Python Launcher (py.exe) could not be found.'
      + #13#10
      + 'Please re-run this setup, or install flextoolslib manually:'
      + #13#10
      + '    py -m pip install flextoolslib';
    Exit;
  end;

  Log('Python ready: ' + PyExePath);
  NeedsPython := False;
end;

procedure InitializeWizard();
var
  Detected, Desc: String;
begin
  // If FLExTools is not yet installed we will install it to the default
  // location, so we know where Modules will be.
  if NeedsFLExTools then
    Detected := ExpandConstant('{localappdata}\FLExTools\Modules')
  else
    Detected := DetectModulesDir();

  if Detected <> '' then
    Desc := 'FLExTools Modules folder found. You can change it if needed.'
  else begin
    Desc := 'Could not locate your FLExTools Modules folder. Please browse to it.';
    Detected := ExpandConstant('{localappdata}\FLExTools\Modules');
  end;

  ModulesDirPage := CreateInputDirPage(
    wpSelectDir,
    'FLExTools Modules Folder',
    'Where should the module be installed?',
    Desc + #13#10#13#10
    + 'This is the Modules subfolder inside your FLExTools installation. '
    + 'After setup, launch FLExTools from the Start Menu and "Split Slash Glosses" '
    + 'will appear in the module list.',
    False, '');
  ModulesDirPage.Add('FLExTools Modules folder:');
  ModulesDirPage.Values[0] := Detected;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ModulesDirPage.ID then begin
    ModulesDir := ModulesDirPage.Values[0];
    if ModulesDir = '' then begin
      MsgBox('Please specify the FLExTools Modules folder.', mbError, MB_OK);
      Result := False;
    end;
    Log('Modules dir confirmed: ' + ModulesDir);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then begin
    // Ensure Modules dir exists before [Files] copies our module into it
    if not DirExists(ModulesDir) then begin
      Log('Creating Modules dir: ' + ModulesDir);
      ForceDirectories(ModulesDir);
    end;
  end;

  if CurStep = ssPostInstall then begin
    // Python is guaranteed available here (PrepareToInstall aborts if not).
    // Install flextoolslib via pip — hidden window, no console needed.
    WizardForm.StatusLabel.Caption := 'Installing flextoolslib Python package...';
    Log('Running: ' + PyExePath + ' -m pip install --upgrade flextoolslib');
    if not Exec(PyExePath, '-m pip install --upgrade flextoolslib',
                '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
      Log('py.exe could not be launched for pip install');
      MsgBox('Could not run pip to install flextoolslib.' + #13#10#13#10
        + 'Please open a command prompt and run:' + #13#10
        + '    py -m pip install flextoolslib',
        mbError, MB_OK);
    end else begin
      Log('pip install exit code: ' + IntToStr(ResultCode));
      if ResultCode <> 0 then
        MsgBox('Could not install flextoolslib automatically (exit code: '
          + IntToStr(ResultCode) + ').' + #13#10#13#10
          + 'Please open a command prompt and run:' + #13#10
          + '    py -m pip install flextoolslib',
          mbError, MB_OK);
    end;
  end;
end;

function GetModulesDir(Param: String): String;
begin
  if ModulesDir <> '' then
    Result := ModulesDir
  else
    Result := ExpandConstant('{localappdata}\FLExTools\Modules');
end;

{ Advise the user about FLExTools/Python/FLEx on uninstall — we never remove them }
procedure DeinitializeUninstall();
begin
  MsgBox('The Split Slash Glosses module has been removed.'
    + #13#10#13#10
    + 'The following were NOT uninstalled (they may be used by other software):'
    + #13#10#13#10
    + '  FLExTools  — delete its folder to remove it:'
    + #13#10
    + '    ' + ExpandConstant('{localappdata}\FLExTools')
    + #13#10
    + '    then run:  py -m pip uninstall flextoolslib'
    + #13#10#13#10
    + '  Python  — uninstall via Settings > Apps > Python'
    + #13#10#13#10
    + '  FLEx  — uninstall via Settings > Apps > FieldWorks',
    mbInformation, MB_OK);
end;
