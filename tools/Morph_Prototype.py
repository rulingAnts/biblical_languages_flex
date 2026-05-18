"""
Morphological Tagging Prototype — FLExTools Module
===================================================
One-time validation script. Tests whether the LCM API supports the four
operations our morphological tagging pipeline depends on:

  TEST 1  LangProject.MsFeatureSystemOA is accessible and writable
          (seed a FsClosedFeature "Tense" + FsSymFeatVal "Aorist")

  TEST 2  MoStemMsa.MsFeaturesOA is settable from Python
          (attach an FsFeatStruc to the MSA)

  TEST 3  FsFeatStruc.GetOrCreateValue() is callable from Python
          (primary path to add FsClosedValue to the feature bundle)
          Falls back to IMoStemMsaFactory + FeatureSpecsOC.Add() if not

  TEST 4  WfiMorphBundle.MorphRA accepts a MoStemAllomorph (not LexEntry)
          (wire a WfiAnalysis to the lexeme form and MSA)

INSTALLATION
  Copy this file to your FLExTools Modules folder, e.g.:
    C:\\...\\FLExTools\\Modules\\Biblical Languages\\Morph_Prototype.py

WHAT TO LOOK FOR AFTER RUNNING
  All four tests should report PASS in the FLExTools output panel.
  Then open the FLEx project and verify:
    • Lexicon:       λύω entry exists with one sense (Grammatical Info visible)
    • Grammar area:  Inflection Features list shows "Tense" with value "Aorist"
    • Wordforms:     ἔλυσεν exists with one Analysis that shows the morph bundle
  This confirms the LCM API hooks are available before we write the full script.

  The module does NOT generate a .flextext — that is a separate prototype step.

NOTE: FLExTools manages the undo task when FTM_ModifiesDB = True, so all
changes made here can be undone with Ctrl+Z inside FLEx after the run.
"""

import logging
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _init_log():
    log_dir = os.path.join(
        os.environ.get('APPDATA', os.path.expanduser('~')),
        'SIL', 'MorphPrototype', 'Logs',
    )
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = os.path.dirname(os.path.abspath(__file__))
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = os.path.join(log_dir, f'MorphPrototype_{ts}.log')
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(asctime)s  %(levelname)-8s  %(message)s'))
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False
    return log_path

LOG_PATH = _init_log()
log = logging.getLogger(__name__)
log.info('=' * 70)
log.info('Morph Prototype — module loaded')
log.info('Python %s', sys.version)

# ---------------------------------------------------------------------------
# FLExTools imports
# ---------------------------------------------------------------------------

try:
    from flextoolslib import (
        FlexToolsModuleClass,
        FTM_Name, FTM_Version, FTM_ModifiesDB,
        FTM_Synopsis, FTM_Help, FTM_Description,
    )
    log.info('flextoolslib imported OK')
except ImportError as e:
    log.critical('flextoolslib not found: %s', e)
    raise

# ---------------------------------------------------------------------------
# LCM imports — wrapped individually so we know which ones are missing
# ---------------------------------------------------------------------------

_IMPORT_ERRORS = []

def _try_import(names, from_module):
    """Import a list of names from a module; record any failures."""
    imported = {}
    for name in names:
        try:
            mod = __import__(from_module, fromlist=[name])
            imported[name] = getattr(mod, name)
            log.debug('Import OK: %s.%s', from_module, name)
        except (ImportError, AttributeError) as e:
            log.warning('Import FAILED: %s.%s — %s', from_module, name, e)
            _IMPORT_ERRORS.append(f'{from_module}.{name}: {e}')
            imported[name] = None
    return imported

_lcm = _try_import([
    'IWfiWordformFactory',
    'IWfiWordformRepository',
    'IWfiAnalysisFactory',
    'IWfiMorphBundleFactory',
    'IWfiGlossFactory',
    'ILexEntryFactory',
    'IMoStemAllomorphFactory',
    'IMoStemMsaFactory',
    'IFsClosedFeatureFactory',
    'IFsSymFeatValFactory',
    'IFsFeatStrucFactory',
    'IFsClosedValueFactory',   # may not exist — we test both paths
], 'SIL.LCModel')

try:
    from SIL.LCModel.Core.Text import TsStringUtils
    log.info('TsStringUtils imported OK')
except ImportError as e:
    log.critical('TsStringUtils not found: %s', e)
    TsStringUtils = None

# ---------------------------------------------------------------------------
# Module metadata
# ---------------------------------------------------------------------------

docs = {
    FTM_Name:        'Morph Prototype',
    FTM_Version:     1,
    FTM_ModifiesDB:  True,
    FTM_Synopsis:    'One-time LCM API validation for morphological tagging pipeline.',
    FTM_Help:        None,
    FTM_Description: __doc__,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(text, ws):
    """Create a TsString for the given writing system handle."""
    return TsStringUtils.MakeString(text, ws)

def _report_pass(report, label):
    report.Info(f'  ✓ PASS  {label}')
    log.info('PASS: %s', label)

def _report_fail(report, label, detail=''):
    report.Warning(f'  ✗ FAIL  {label}' + (f' — {detail}' if detail else ''))
    log.warning('FAIL: %s  detail=%s', label, detail)

def _report_section(report, title):
    report.Info('')
    report.Info(f'── {title} ──')
    log.info('=== %s ===', title)

# ---------------------------------------------------------------------------
# TEST 1 — Seed LangProject.MsFeatureSystemOA
# ---------------------------------------------------------------------------

def _test1_seed_feature_system(project, cache, ws_en, report):
    """
    Tries to create one FsClosedFeature ("Tense") with one FsSymFeatVal
    ("Aorist") under LangProject.MsFeatureSystemOA.

    Returns (tense_feat, aorist_val) on success, (None, None) on failure.
    """
    _report_section(report, 'TEST 1 — Seed LangProject.MsFeatureSystemOA')

    # 1a. Access MsFeatureSystemOA
    try:
        feat_system = project.lp.MsFeatureSystemOA
        if feat_system is None:
            _report_fail(report, 'project.lp.MsFeatureSystemOA', 'returned None')
            return None, None
        _report_pass(report, 'project.lp.MsFeatureSystemOA accessible')
        log.debug('MsFeatureSystemOA hvo=%s', feat_system.Hvo)
    except Exception as e:
        _report_fail(report, 'project.lp.MsFeatureSystemOA', str(e))
        log.exception('MsFeatureSystemOA access failed')
        return None, None

    # 1b. Create FsClosedFeature factory
    factory_cf = _lcm['IFsClosedFeatureFactory']
    if factory_cf is None:
        _report_fail(report, 'IFsClosedFeatureFactory import', 'not importable')
        return None, None

    try:
        cf_factory = cache.ServiceLocator.GetService(factory_cf)
        _report_pass(report, 'IFsClosedFeatureFactory.GetService()')
    except Exception as e:
        _report_fail(report, 'IFsClosedFeatureFactory.GetService()', str(e))
        log.exception('IFsClosedFeatureFactory failed')
        return None, None

    # 1c. Create the "Tense" FsClosedFeature
    try:
        tense_feat = cf_factory.Create()
        feat_system.FeaturesOC.Add(tense_feat)
        tense_feat.Name.set_String(ws_en, _ts('Tense', ws_en))
        tense_feat.Abbreviation.set_String(ws_en, _ts('Tns', ws_en))
        _report_pass(report, 'Create FsClosedFeature "Tense" + add to FeaturesOC')
        log.debug('tense_feat hvo=%s', tense_feat.Hvo)
    except Exception as e:
        _report_fail(report, 'Create FsClosedFeature "Tense"', str(e))
        log.exception('FsClosedFeature creation failed')
        return None, None

    # 1d. Create FsSymFeatVal factory
    factory_sv = _lcm['IFsSymFeatValFactory']
    if factory_sv is None:
        _report_fail(report, 'IFsSymFeatValFactory import', 'not importable')
        return tense_feat, None

    try:
        sv_factory = cache.ServiceLocator.GetService(factory_sv)
        _report_pass(report, 'IFsSymFeatValFactory.GetService()')
    except Exception as e:
        _report_fail(report, 'IFsSymFeatValFactory.GetService()', str(e))
        log.exception('IFsSymFeatValFactory failed')
        return tense_feat, None

    # 1e. Create the "Aorist" FsSymFeatVal
    try:
        aorist_val = sv_factory.Create()
        tense_feat.ValuesOC.Add(aorist_val)
        aorist_val.Name.set_String(ws_en, _ts('Aorist', ws_en))
        aorist_val.Abbreviation.set_String(ws_en, _ts('Aor', ws_en))
        _report_pass(report, 'Create FsSymFeatVal "Aorist" + add to ValuesOC')
        log.debug('aorist_val hvo=%s', aorist_val.Hvo)
    except Exception as e:
        _report_fail(report, 'Create FsSymFeatVal "Aorist"', str(e))
        log.exception('FsSymFeatVal creation failed')
        return tense_feat, None

    return tense_feat, aorist_val

# ---------------------------------------------------------------------------
# TEST 2 — Create LexEntry with MoStemAllomorph + MoStemMsa
# TEST 4 — WfiMorphBundle.MorphRA accepts MoStemAllomorph
# (Tests 2 and 4 share object creation so are done together)
# ---------------------------------------------------------------------------

def _test2_and_4_create_lex_entry(project, cache, ws_grc, ws_en, report):
    """
    Creates LexEntry λύω with:
      - LexemeFormOA = MoStemAllomorph (form "λύω")
      - MorphoSyntaxAnalysesOC → MoStemMsa

    Also creates WfiWordform ἔλυσεν + WfiAnalysis + WfiMorphBundle and sets:
      - bundle.MorphRA = allomorph   (TEST 4)
      - bundle.MsaRA   = msa

    Returns (allomorph, msa, analysis) on success; any may be None on partial failure.
    """
    _report_section(report, 'TEST 2 & 4 — LexEntry + MoStemAllomorph + MoStemMsa + WfiMorphBundle')

    allomorph = None
    msa       = None
    analysis  = None

    # 2a. Create LexEntry
    factory_le = _lcm['ILexEntryFactory']
    if factory_le is None:
        _report_fail(report, 'ILexEntryFactory import', 'not importable')
        return allomorph, msa, analysis

    try:
        le_factory = cache.ServiceLocator.GetService(factory_le)
        entry = le_factory.Create()
        _report_pass(report, 'ILexEntryFactory.Create() — LexEntry')
        log.debug('entry hvo=%s', entry.Hvo)
    except Exception as e:
        _report_fail(report, 'ILexEntryFactory.Create()', str(e))
        log.exception('LexEntry creation failed')
        return allomorph, msa, analysis

    # 2b. Create MoStemAllomorph and set as LexemeFormOA
    factory_am = _lcm['IMoStemAllomorphFactory']
    if factory_am is None:
        _report_fail(report, 'IMoStemAllomorphFactory import', 'not importable')
    else:
        try:
            am_factory = cache.ServiceLocator.GetService(factory_am)
            allomorph  = am_factory.Create()
            entry.LexemeFormOA = allomorph
            allomorph.Form.set_String(ws_grc, _ts('λύω', ws_grc))
            _report_pass(report, 'IMoStemAllomorphFactory.Create() + entry.LexemeFormOA = allomorph')
            log.debug('allomorph hvo=%s', allomorph.Hvo)
        except Exception as e:
            _report_fail(report, 'Create MoStemAllomorph / set LexemeFormOA', str(e))
            log.exception('MoStemAllomorph creation failed')
            allomorph = None

    # Try to set morph type to "stem" (optional; log result but don't fail the test)
    if allomorph is not None:
        try:
            morph_types = project.lp.MorphologicalDataOA.MorphTypesOA.PossibilitiesOS
            for mt in morph_types:
                try:
                    name = mt.Name.BestAnalysisAlternative.Text or ''
                except Exception:
                    name = ''
                if 'stem' in name.lower():
                    allomorph.MorphTypeRA = mt
                    log.info('Set MorphTypeRA to stem type: %r', name)
                    break
            else:
                log.info('No "stem" morph type found — MorphTypeRA left unset')
        except Exception as e:
            log.warning('Could not set MorphTypeRA: %s', e)

    # 2c. Create MoStemMsa and add to entry
    factory_ms = _lcm['IMoStemMsaFactory']
    if factory_ms is None:
        _report_fail(report, 'IMoStemMsaFactory import', 'not importable')
    else:
        try:
            ms_factory = cache.ServiceLocator.GetService(factory_ms)
            msa        = ms_factory.Create()
            entry.MorphoSyntaxAnalysesOC.Add(msa)
            _report_pass(report, 'IMoStemMsaFactory.Create() + MorphoSyntaxAnalysesOC.Add(msa)')
            log.debug('msa hvo=%s', msa.Hvo)
        except Exception as e:
            _report_fail(report, 'Create MoStemMsa / add to MorphoSyntaxAnalysesOC', str(e))
            log.exception('MoStemMsa creation failed')
            msa = None

    # 4. Create WfiWordform + WfiAnalysis + WfiMorphBundle and test MorphRA
    factory_wf = _lcm['IWfiWordformFactory']
    factory_wa = _lcm['IWfiAnalysisFactory']
    factory_mb = _lcm['IWfiMorphBundleFactory']
    factory_wg = _lcm['IWfiGlossFactory']

    if None in (factory_wf, factory_wa, factory_mb, factory_wg):
        _report_fail(report, 'WfiWordform/Analysis/MorphBundle/Gloss factories import',
                     'one or more not importable')
        return allomorph, msa, analysis

    try:
        wf_factory = cache.ServiceLocator.GetService(factory_wf)
        wa_factory = cache.ServiceLocator.GetService(factory_wa)
        mb_factory = cache.ServiceLocator.GetService(factory_mb)
        wg_factory = cache.ServiceLocator.GetService(factory_wg)

        wordform = wf_factory.Create()
        wordform.Form.set_String(ws_grc, _ts('ἔλυσεν', ws_grc))
        _report_pass(report, 'IWfiWordformFactory.Create() + set Form "ἔλυσεν"')
        log.debug('wordform hvo=%s', wordform.Hvo)

        analysis = wa_factory.Create()
        wordform.AnalysesOC.Add(analysis)
        _report_pass(report, 'IWfiAnalysisFactory.Create() + AnalysesOC.Add(analysis)')
        log.debug('analysis hvo=%s  guid=%s', analysis.Hvo, analysis.Guid)

        gloss = wg_factory.Create()
        analysis.MeaningsOC.Add(gloss)
        gloss.Form.set_String(ws_en, _ts('he loosed', ws_en))
        _report_pass(report, 'IWfiGlossFactory.Create() + MeaningsOC.Add + set Form "he loosed"')
        log.debug('gloss hvo=%s', gloss.Hvo)

        bundle = mb_factory.Create()
        analysis.MorphBundlesOS.Add(bundle)
        _report_pass(report, 'IWfiMorphBundleFactory.Create() + MorphBundlesOS.Add(bundle)')
        log.debug('bundle hvo=%s', bundle.Hvo)

        # TEST 4: set MorphRA to the MoStemAllomorph (key question)
        if allomorph is not None:
            try:
                bundle.MorphRA = allomorph
                _report_pass(report, 'TEST 4: bundle.MorphRA = allomorph (MoStemAllomorph) ✓')
                log.info('TEST 4 PASS: MorphRA accepts MoStemAllomorph')
            except Exception as e:
                _report_fail(report, 'TEST 4: bundle.MorphRA = allomorph', str(e))
                log.exception('TEST 4 FAIL: MorphRA assignment failed')
        else:
            report.Warning('  TEST 4 skipped — allomorph not created')

        # Set MsaRA to the MoStemMsa
        if msa is not None:
            try:
                bundle.MsaRA = msa
                _report_pass(report, 'bundle.MsaRA = msa (MoStemMsa)')
                log.info('MsaRA assignment OK')
            except Exception as e:
                _report_fail(report, 'bundle.MsaRA = msa', str(e))
                log.exception('MsaRA assignment failed')

    except Exception as e:
        _report_fail(report, 'WfiWordform/Analysis/Bundle creation', str(e))
        log.exception('Wfi* creation failed')
        analysis = None

    return allomorph, msa, analysis

# ---------------------------------------------------------------------------
# TEST 2 (continued) + TEST 3 — MsFeaturesOA + GetOrCreateValue
# ---------------------------------------------------------------------------

def _test2_and_3_set_features(cache, msa, tense_feat, aorist_val, report):
    """
    Attaches an FsFeatStruc to msa.MsFeaturesOA (TEST 2), then tries
    two approaches to add Tense=Aorist to it:

      Primary   (TEST 3a): fs.GetOrCreateValue(tense_feat)
      Fallback  (TEST 3b): IFsClosedValueFactory → FeatureSpecsOC.Add()

    Reports which path succeeds so we know which to use in the real script.
    """
    _report_section(report, 'TEST 2 & 3 — MsFeaturesOA + FsClosedValue assignment')

    if msa is None:
        report.Warning('  Skipped — MoStemMsa not available from previous test')
        return
    if tense_feat is None or aorist_val is None:
        report.Warning('  Skipped — Tense feature / Aorist value not available from TEST 1')
        return

    # 2d. Create FsFeatStruc
    factory_fs = _lcm['IFsFeatStrucFactory']
    if factory_fs is None:
        _report_fail(report, 'IFsFeatStrucFactory import', 'not importable')
        return

    try:
        fs_factory = cache.ServiceLocator.GetService(factory_fs)
        feat_struc = fs_factory.Create()
        _report_pass(report, 'IFsFeatStrucFactory.Create() — FsFeatStruc')
        log.debug('feat_struc hvo=%s', feat_struc.Hvo)
    except Exception as e:
        _report_fail(report, 'IFsFeatStrucFactory.Create()', str(e))
        log.exception('FsFeatStruc creation failed')
        return

    # TEST 2: set msa.MsFeaturesOA = feat_struc
    try:
        msa.MsFeaturesOA = feat_struc
        _report_pass(report, 'TEST 2: msa.MsFeaturesOA = feat_struc  (direct assignment) ✓')
        log.info('TEST 2 PASS: MsFeaturesOA direct assignment works')
    except Exception as e:
        _report_fail(report, 'TEST 2: msa.MsFeaturesOA = feat_struc', str(e))
        log.warning('TEST 2 FAIL direct assignment: %s', e)

        # Fallback: use DomainDataByFlid
        report.Info('  Trying fallback: DomainDataByFlid.SetObjProp …')
        try:
            from SIL.LCModel import MoStemMsaTags
            flid = MoStemMsaTags.kflidMsFeaturesOA
            cache.DomainDataByFlid.SetObjProp(msa.Hvo, flid, feat_struc.Hvo)
            _report_pass(report, 'TEST 2 fallback: DomainDataByFlid.SetObjProp ✓')
            log.info('TEST 2 fallback PASS')
        except Exception as e2:
            _report_fail(report, 'TEST 2 fallback: DomainDataByFlid.SetObjProp', str(e2))
            log.exception('TEST 2 both paths failed')
            return

    # TEST 3a: fs.GetOrCreateValue(tense_feat) — primary path
    report.Info('')
    report.Info('  TEST 3a — primary path: feat_struc.GetOrCreateValue(tense_feat)')
    closed_val = None
    try:
        closed_val = feat_struc.GetOrCreateValue(tense_feat)
        _report_pass(report, 'TEST 3a: feat_struc.GetOrCreateValue(tense_feat) ✓')
        log.info('TEST 3a PASS: GetOrCreateValue works')
    except AttributeError as e:
        _report_fail(report, 'TEST 3a: feat_struc.GetOrCreateValue()', str(e))
        log.warning('TEST 3a FAIL (AttributeError — method not visible from Python): %s', e)
    except Exception as e:
        _report_fail(report, 'TEST 3a: feat_struc.GetOrCreateValue()', str(e))
        log.warning('TEST 3a FAIL: %s', e)

    if closed_val is None:
        # TEST 3b: fallback via IFsClosedValueFactory
        report.Info('  TEST 3b — fallback path: IFsClosedValueFactory + FeatureSpecsOC.Add()')
        factory_cv = _lcm['IFsClosedValueFactory']
        if factory_cv is None:
            _report_fail(report, 'TEST 3b: IFsClosedValueFactory import', 'not importable')
            report.Warning('  Both GetOrCreateValue paths failed — will need further investigation')
            return
        try:
            cv_factory = cache.ServiceLocator.GetService(factory_cv)
            closed_val = cv_factory.Create()
            feat_struc.FeatureSpecsOC.Add(closed_val)
            _report_pass(report, 'TEST 3b: IFsClosedValueFactory.Create() + FeatureSpecsOC.Add() ✓')
            log.info('TEST 3b PASS: fallback factory path works')
        except Exception as e:
            _report_fail(report, 'TEST 3b: IFsClosedValueFactory fallback', str(e))
            log.exception('TEST 3b FAIL')
            return

    # Set FeatureRA and ValueRA on whichever closed_val we got
    try:
        closed_val.FeatureRA = tense_feat
        closed_val.ValueRA   = aorist_val
        _report_pass(report, 'closed_val.FeatureRA = tense_feat  +  closed_val.ValueRA = aorist_val')
        log.info('FeatureRA/ValueRA assignment OK')
    except Exception as e:
        _report_fail(report, 'Set FeatureRA / ValueRA on FsClosedValue', str(e))
        log.exception('FeatureRA/ValueRA assignment failed')

# ---------------------------------------------------------------------------
# Summary + GUID output
# ---------------------------------------------------------------------------

def _print_summary(project, report, analysis):
    _report_section(report, 'Summary')

    if _IMPORT_ERRORS:
        report.Info(f'  Import warnings ({len(_IMPORT_ERRORS)}):')
        for err in _IMPORT_ERRORS:
            report.Warning(f'    {err}')
    else:
        report.Info('  All LCM imports succeeded.')

    if analysis is not None:
        guid_str = str(analysis.Guid).upper()
        report.Info('')
        report.Info(f'  WfiAnalysis GUID: {{{guid_str}}}')
        report.Info('  (You will need this GUID for the .flextext prototype step)')
        log.info('WfiAnalysis GUID: %s', guid_str)

    report.Info('')
    report.Info('  Now open FLEx and verify:')
    report.Info('    • Lexicon:      λύω entry exists with a sense')
    report.Info('    • Grammar:      Inflection Features list shows "Tense" → "Aorist"')
    report.Info('    • Wordforms:    ἔλυσεν exists with one analysis + morph bundle')
    report.Info(f'  Log file: {LOG_PATH}')

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def Main(project, report, modifyAllowed):
    log.info('Main() called  modifyAllowed=%s', modifyAllowed)

    if not modifyAllowed:
        report.Warning('This module must be run in Modify mode — click the Modify button.')
        return

    report.Info('Morph Prototype — validating LCM API hooks for morphological tagging')
    report.Info(f'Log: {LOG_PATH}')

    if TsStringUtils is None:
        report.Error('TsStringUtils not available — cannot run. Is FLEx installed?')
        return

    cache  = project.project
    ws_en  = project.lp.DefaultAnalysisWritingSystem.Handle
    ws_grc = project.lp.DefaultVernacularWritingSystem.Handle
    log.info('ws_en=%s  ws_grc=%s', ws_en, ws_grc)

    # Run tests
    tense_feat, aorist_val = _test1_seed_feature_system(project, cache, ws_en, report)
    allomorph, msa, analysis = _test2_and_4_create_lex_entry(project, cache, ws_grc, ws_en, report)
    _test2_and_3_set_features(cache, msa, tense_feat, aorist_val, report)
    _print_summary(project, report, analysis)

    log.info('Main() finished')
    log.info('=' * 70)

# ---------------------------------------------------------------------------
# FLExTools registration
# ---------------------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(runFunction=Main, docs=docs)

if __name__ == '__main__':
    print(FlexToolsModule.Help())
