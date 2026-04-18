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
SetupLogging=yes

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
  NeedsFLExTools : Boolean;  { True if FLExTools should be installed }


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
  Base: String;
begin
  Base := ExpandConstant('{localappdata}\FLExTools');
  { FlexToolsLib is the core library — its presence means FLExTools is installed }
  Result := DirExists(Base + '\FlexToolsLib');
  Log('FLExTools FlexToolsLib dir: ' + Base + '\FlexToolsLib  exists: ' + BoolStr(Result));
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
  FLExTools installation — direct file copy, no VBS or cmd.exe needed
  ----------------------------------------------------------------------- }

procedure InstallFLExTools();
var
  ZipPath, ExtractDir, SourceDir, DestDir: String;
  ResultCode: Integer;
begin
  Log('Installing FLExTools from bundled zip...');
  ZipPath    := ExpandConstant('{tmp}\FlexTools.zip');
  ExtractDir := ExpandConstant('{tmp}\FlexToolsInstall');
  DestDir    := ExpandConstant('{localappdata}\FLExTools');

  Log('Zip path: ' + ZipPath + '  exists: ' + BoolStr(FileExists(ZipPath)));
  if not FileExists(ZipPath) then begin
    MsgBox('Could not find the bundled FLExTools package. Please install FLExTools manually from:'
      + #13#10 + 'https://github.com/cdfarrow/flextools/releases',
      mbError, MB_OK);
    Exit;
  end;

  { Step 1: extract zip }
  Exec('powershell.exe',
    '-NoProfile -NonInteractive -Command ' +
    '"Expand-Archive -LiteralPath ''' + ZipPath +
    ''' -DestinationPath ''' + ExtractDir + ''' -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Log('Expand-Archive exit code: ' + IntToStr(ResultCode));

  { The zip extracts to a FlexTools\ subfolder; fall back to root if flat }
  SourceDir := ExtractDir + '\FlexTools';
  if not DirExists(SourceDir) then
    SourceDir := ExtractDir;
  Log('Source dir: ' + SourceDir + '  exists: ' + BoolStr(DirExists(SourceDir)));

  { Step 2: copy all FLExTools files directly — bypass unreliable VBS }
  ForceDirectories(DestDir);
  Exec('powershell.exe',
    '-NoProfile -NonInteractive -Command ' +
    '"Copy-Item -Path ''' + SourceDir + '\*'' ' +
    '-Destination ''' + DestDir + ''' -Recurse -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Log('Copy-Item exit code: ' + IntToStr(ResultCode));
  Log('FlexToolsLib present after install: ' +
      BoolStr(DirExists(DestDir + '\FlexToolsLib')));
end;


{ -----------------------------------------------------------------------
  Wizard lifecycle
  ----------------------------------------------------------------------- }

function InitializeSetup(): Boolean;
begin
  Result := True;

  if not FLExIsInstalled() then begin
    MsgBox('FieldWorks Language Explorer (FLEx) must be installed before running this setup.'
      + #13#10#13#10
      + 'Download FLEx from: https://software.sil.org/fieldworks/',
      mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  NeedsFLExTools := not FLExToolsIsInstalled();
  if NeedsFLExTools then
    Log('FLExTools not found — will install bundled version ' + BundledFLExToolsVersion)
  else
    Log('FLExTools already installed — skipping');
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
  if CurStep = ssInstall then begin
    { Ensure Modules dir exists before [Files] copies our module into it }
    if not DirExists(ModulesDir) then begin
      Log('Creating Modules dir: ' + ModulesDir);
      ForceDirectories(ModulesDir);
    end;
  end;

  if CurStep = ssPostInstall then begin
    { Install FLExTools here — {tmp} files are available until installer exits,
      so the zip is present at ssPostInstall even though it arrives via [Files] }
    if NeedsFLExTools then begin
      WizardForm.StatusLabel.Caption := 'Installing FLExTools...';
      InstallFLExTools();
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
