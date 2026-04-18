; FLEx Gloss Splitter — FLExTools Module Installer
; Inno Setup 6  (https://jrsoftware.org/isinfo.php)
;
; What this installer does:
;   1. Verifies FLEx is installed (aborts with friendly message if not)
;   2. Installs FLExTools if missing, or upgrades it if our bundled version
;      is newer than whatever is already installed.  Uses FLExTools' own
;      InstallOrUpdate.vbs so FLExTools remains independently managed.
;      Never downgrades an existing newer FLExTools installation.
;   3. Copies Split_Slash_Glosses.py into the FLExTools Modules folder.
;   4. Uninstaller removes only Split_Slash_Glosses.py and itself.
;      FLExTools is left in place; a message advises the user how to
;      remove it separately if they wish.
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

UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; FLExTools zip — extracted to temp during install, deleted afterward
; (FLExTools' own InstallOrUpdate.vbs manages the actual installation)
Source: "FlexTools.zip"; DestDir: "{tmp}"; Flags: deleteafterinstall

; FLExTools LICENSE — required by LGPL 2.1 for redistribution
Source: "FlexTools_LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; Our module — copied to the FLExTools Modules folder
Source: "..\tools\{#ModuleFile}"; DestDir: "{code:GetModulesDir}"; \
    Flags: ignoreversion

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
Filename: "explorer.exe"; Parameters: "{code:GetModulesDir}"; \
    Description: "Open the Modules folder in Explorer"; \
    Flags: nowait postinstall skipifsilent unchecked

[Messages]
FinishedLabel=The Split Slash Glosses module has been installed.%n%nRestart FLExTools and you will find "Split Slash Glosses" in the module list.

; -------------------------------------------------------------------------
; Code
; -------------------------------------------------------------------------
[Code]

const
  { Version of FLExTools bundled with this installer — set at compile time }
  BundledFLExToolsVersion = '{#FLEXTOOLS_VERSION}';

{ BoolToStr is not a built-in in Inno Setup Pascal }
function BoolStr(B: Boolean): String;
begin
  if B then Result := 'True' else Result := 'False';
end;

var
  ModulesDirPage : TInputDirWizardPage;
  ModulesDir     : String;
  PythonExe      : String;   { Python executable found at init time }
  NeedsFLExTools : Boolean;  { True if FLExTools should be installed/upgraded }


{ -----------------------------------------------------------------------
  Version helpers
  ----------------------------------------------------------------------- }

{ Split a "X.Y.Z" string into its integer parts. Missing parts default 0. }
procedure ParseVersion(V: String; var Major, Minor, Patch: Integer);
var
  P: Integer;
begin
  Major := 0; Minor := 0; Patch := 0;
  P := Pos('.', V);
  if P = 0 then begin Major := StrToIntDef(V, 0); Exit; end;
  Major := StrToIntDef(Copy(V, 1, P-1), 0);
  V := Copy(V, P+1, Length(V));
  P := Pos('.', V);
  if P = 0 then begin Minor := StrToIntDef(V, 0); Exit; end;
  Minor := StrToIntDef(Copy(V, 1, P-1), 0);
  Patch := StrToIntDef(Copy(V, P+1, Length(V)), 0);
end;

{ Return 1 if A > B, -1 if A < B, 0 if equal. }
function CompareVersions(A, B: String): Integer;
var
  Ma, Mi, Pa, Mb, Mib, Pb: Integer;
begin
  ParseVersion(A, Ma, Mi, Pa);
  ParseVersion(B, Mb, Mib, Pb);
  if Ma <> Mb then begin if Ma > Mb then Result := 1 else Result := -1; Exit; end;
  if Mi <> Mib then begin if Mi > Mib then Result := 1 else Result := -1; Exit; end;
  if Pa <> Pb then begin if Pa > Pb then Result := 1 else Result := -1; Exit; end;
  Result := 0;
end;


{ -----------------------------------------------------------------------
  FLEx detection
  ----------------------------------------------------------------------- }

function GetFLExInstallDir(): String;
var
  InstallDir: String;
  FindRec: TFindRec;
  SilDir: String;
begin
  Result := '';

  { Try registry — attempt both 64-bit and 32-bit views.
    FLEx 9.x is 64-bit; on a 32-bit Inno Setup process HKLM reads the WOW node,
    so we also pass the 64-bit override flag ($01000000). }
  if RegQueryStringValue(HKLM, 'SOFTWARE\SIL\FieldWorks', 'RootDir', InstallDir) and
     (InstallDir <> '') then
    begin Log('FLEx dir from registry (32-bit view): ' + InstallDir); Result := InstallDir; Exit; end;
  if RegQueryStringValue(HKLM or $01000000, 'SOFTWARE\SIL\FieldWorks', 'RootDir', InstallDir) and
     (InstallDir <> '') then
    begin Log('FLEx dir from registry (64-bit view): ' + InstallDir); Result := InstallDir; Exit; end;

  { Filesystem fallback: FLEx installs to a versioned path like
    C:\Program Files\SIL\FieldWorks 9.0.17 — scan for any matching dir. }
  SilDir := ExpandConstant('{pf}\SIL\');
  if FindFirst(SilDir + 'FieldWorks*', FindRec) then begin
    try
      repeat
        if (FindRec.Attributes and $10) <> 0 then begin   { FILE_ATTRIBUTE_DIRECTORY }
          Log('FLEx candidate: ' + SilDir + FindRec.Name);
          if FileExists(SilDir + FindRec.Name + '\FieldWorks.exe') then begin
            Result := SilDir + FindRec.Name;
            Log('FLEx found by scan: ' + Result);
            Exit;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;

  SilDir := ExpandConstant('{pf32}\SIL\');
  if FindFirst(SilDir + 'FieldWorks*', FindRec) then begin
    try
      repeat
        if (FindRec.Attributes and $10) <> 0 then begin
          if FileExists(SilDir + FindRec.Name + '\FieldWorks.exe') then begin
            Result := SilDir + FindRec.Name;
            Log('FLEx found by scan (pf32): ' + Result);
            Exit;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;

  Log('FLEx install dir not found');
end;

function FLExIsInstalled(): Boolean;
begin
  Result := GetFLExInstallDir() <> '';
  Log('FLEx installed: ' + BoolStr(Result));
end;


{ -----------------------------------------------------------------------
  Python detection
  ----------------------------------------------------------------------- }

function FindPython(): String;
var
  FLExDir, Candidate: String;
  ResultCode: Integer;
begin
  Result := '';

  { Check known FLEx Python locations first }
  FLExDir := GetFLExInstallDir();
  if FLExDir <> '' then begin
    Candidate := FLExDir + '\Python\python.exe';
    if FileExists(Candidate) then begin Log('Found Python: ' + Candidate); Result := Candidate; Exit; end;
    Candidate := FLExDir + '\Python3\python.exe';
    if FileExists(Candidate) then begin Log('Found Python: ' + Candidate); Result := Candidate; Exit; end;
    Candidate := FLExDir + '\lib\python\python.exe';
    if FileExists(Candidate) then begin Log('Found Python: ' + Candidate); Result := Candidate; Exit; end;
  end;

  { Fall back to system Python via where.exe }
  Exec(ExpandConstant('{sys}\where.exe'), 'python',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if ResultCode = 0 then begin
    Log('Using system Python from PATH');
    Result := 'python';   { will be found on PATH }
  end else
    Log('Python not found');
end;


{ -----------------------------------------------------------------------
  Run a command and capture its stdout to a temp file.
  Returns True if the process exited with code 0.
  ----------------------------------------------------------------------- }
function RunAndCapture(ExeName, Params: String; var Output: String): Boolean;
var
  TempFile: String;
  Lines: TArrayOfString;
  I, ResultCode: Integer;
begin
  Output := '';
  TempFile := ExpandConstant('{tmp}\capture.txt');
  Result := Exec(ExpandConstant('{cmd}'),
    '/c "' + ExeName + '" ' + Params + ' > "' + TempFile + '" 2>&1',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
  if LoadStringsFromFile(TempFile, Lines) then
    for I := 0 to GetArrayLength(Lines)-1 do
      Output := Output + Trim(Lines[I]) + ' ';
  Output := Trim(Output);
  DeleteFile(TempFile);
  Log('RunAndCapture "' + ExeName + ' ' + Params + '" -> ' +
      BoolStr(Result) + ' output: ' + Output);
end;


{ -----------------------------------------------------------------------
  FLExTools version detection
  ----------------------------------------------------------------------- }

function GetInstalledFLExToolsVersion(): String;
var
  Output: String;
begin
  Result := '0.0.0';
  if PythonExe = '' then Exit;

  { Ask Python to import flextoolslib and report its version }
  RunAndCapture(PythonExe,
    '-c "import flextoolslib; print(flextoolslib.__version__)"',
    Output);

  { Output should be a bare version string, e.g. "2.3.2" }
  if (Output <> '') and (Pos(' ', Trim(Output)) = 0) then
    Result := Trim(Output);

  Log('Installed FLExTools version: ' + Result);
end;

function FLExToolsIsInstalled(): Boolean;
var
  Output: String;
begin
  Result := False;
  if PythonExe = '' then Exit;
  RunAndCapture(PythonExe,
    '-c "import flextoolslib; print(''ok'')"', Output);
  Result := Pos('ok', Output) > 0;
  Log('FLExTools importable: ' + BoolStr(Result));
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
  FLExTools installation (via its own InstallOrUpdate.vbs)
  ----------------------------------------------------------------------- }

procedure InstallFLExTools();
var
  ZipPath, ExtractDir, VBSPath: String;
  ResultCode: Integer;
begin
  Log('Installing FLExTools from bundled zip...');
  ZipPath   := ExpandConstant('{tmp}\FlexTools.zip');
  ExtractDir := ExpandConstant('{tmp}\FlexToolsInstall');

  { Extract zip using PowerShell }
  Exec('powershell.exe',
    '-NoProfile -Command "Expand-Archive -Path ''' + ZipPath +
    ''' -DestinationPath ''' + ExtractDir + ''' -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if ResultCode <> 0 then begin
    Log('Zip extraction failed (code ' + IntToStr(ResultCode) + ')');
    MsgBox('Could not extract FLExTools. Please install FLExTools manually from:'
      + #13#10 + 'https://github.com/cdfarrow/flextools/releases',
      mbError, MB_OK);
    Exit;
  end;

  { FLExTools zip extracts to a "FlexTools" subfolder }
  VBSPath := ExtractDir + '\FlexTools\InstallOrUpdate.vbs';
  if not FileExists(VBSPath) then begin
    Log('InstallOrUpdate.vbs not found at: ' + VBSPath);
    MsgBox('FLExTools installer script not found. Please install FLExTools manually from:'
      + #13#10 + 'https://github.com/cdfarrow/flextools/releases',
      mbError, MB_OK);
    Exit;
  end;

  Log('Running FLExTools InstallOrUpdate.vbs from: ' + VBSPath);
  Exec('wscript.exe', '"' + VBSPath + '"',
       ExtractDir + '\FlexTools', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
  Log('InstallOrUpdate.vbs exited with code: ' + IntToStr(ResultCode));
end;


{ -----------------------------------------------------------------------
  Wizard lifecycle
  ----------------------------------------------------------------------- }

function InitializeSetup(): Boolean;
var
  InstalledVer: String;
begin
  Result := True;

  { Abort if FLEx is not installed }
  if not FLExIsInstalled() then begin
    MsgBox('FieldWorks Language Explorer (FLEx) must be installed before running this setup.'
      + #13#10#13#10
      + 'Download FLEx from: https://software.sil.org/fieldworks/',
      mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  PythonExe := FindPython();

  { Decide whether we need to install / upgrade FLExTools }
  if not FLExToolsIsInstalled() then begin
    Log('FLExTools not installed — will install bundled version ' + BundledFLExToolsVersion);
    NeedsFLExTools := True;
  end else begin
    InstalledVer := GetInstalledFLExToolsVersion();
    if CompareVersions(BundledFLExToolsVersion, InstalledVer) > 0 then begin
      Log('Bundled FLExTools (' + BundledFLExToolsVersion + ') is newer than installed ('
          + InstalledVer + ') — will upgrade');
      NeedsFLExTools := True;
    end else begin
      Log('Installed FLExTools (' + InstalledVer + ') is current or newer — skipping');
      NeedsFLExTools := False;
    end;
  end;
end;

procedure InitializeWizard();
var
  Detected, Desc: String;
begin
  { If FLExTools is not yet installed we will install it to the default
    location, so we know where Modules will be. }
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
    + 'After setup, restart FLExTools and "Split Slash Glosses" will appear '
    + 'in the module list.',
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
begin
  { Install / upgrade FLExTools just before our files are copied }
  if CurStep = ssInstall then begin
    if NeedsFLExTools then begin
      WizardForm.StatusLabel.Caption := 'Installing FLExTools...';
      InstallFLExTools();
      { Re-detect Modules dir in case FLExTools installed somewhere unexpected }
      if not DirExists(ModulesDir) then begin
        Log('Modules dir does not exist after FLExTools install — re-detecting');
        ModulesDir := DetectModulesDir();
        if ModulesDir = '' then
          ModulesDir := ExpandConstant('{localappdata}\FLExTools\Modules');
        Log('Using Modules dir: ' + ModulesDir);
        ForceDirectories(ModulesDir);
      end;
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

{ Advise the user about FLExTools on uninstall — we never remove it }
procedure DeinitializeUninstall();
begin
  MsgBox('The Split Slash Glosses module has been removed.'
    + #13#10#13#10
    + 'FLExTools was not uninstalled — it may be used by other modules.'
    + #13#10
    + 'If you no longer need FLExTools, you can remove it by deleting its folder'
    + #13#10
    + '(usually: ' + ExpandConstant('{localappdata}\FLExTools') + ')'
    + #13#10
    + 'and running:  pip uninstall flextoolslib',
    mbInformation, MB_OK);
end;
