from pathlib import Path
import json
import os
import sys

import pytest
from baldr_launcher import configure_portable


def isolate(monkeypatch, tmp_path):
    for key in ('BALDR_CONFIG','DATA_ROOT','OUTPUT_ROOT','RESEARCH_STATE_ROOT','MPLCONFIGDIR','PERSONAL_MODEL_POLICY_PATH'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'local'))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'package'/'baldr.exe'))


def test_first_start_uses_external_empty_roots_without_dotenv(monkeypatch, tmp_path):
    isolate(monkeypatch,tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path/'.env').write_text('DATA_ROOT=D:/private\n',encoding='utf-8')
    path,configured=configure_portable()
    assert not configured
    assert path == tmp_path/'local'/'baldr'/'config.json'
    assert Path(os.environ['DATA_ROOT']) == tmp_path/'local'/'baldr'/'market'
    assert 'PERSONAL_MODEL_POLICY_PATH' not in os.environ


def test_json_preserves_environment_and_original_model_selection(monkeypatch,tmp_path):
    isolate(monkeypatch,tmp_path)
    config=tmp_path/'settings.json'
    config.write_text(json.dumps({'DATA_ROOT':str(tmp_path/'market'),'OUTPUT_ROOT':str(tmp_path/'results'),
                                 'PERSONAL_MODEL_POLICY_PATH':str(tmp_path/'original policy.json')}),encoding='utf-8')
    monkeypatch.setenv('BALDR_CONFIG',str(config))
    monkeypatch.setenv('DATA_ROOT',str(tmp_path/'explicit market'))
    _,configured=configure_portable()
    assert configured
    assert os.environ['DATA_ROOT'] == str(tmp_path/'explicit market')
    assert os.environ['PERSONAL_MODEL_POLICY_PATH'] == str(tmp_path/'original policy.json')


@pytest.mark.parametrize('value',['relative',None])
def test_invalid_config_fails_before_using_default(monkeypatch,tmp_path,value):
    isolate(monkeypatch,tmp_path)
    config=tmp_path/'settings.json'
    config.write_text(json.dumps({'DATA_ROOT':value}),encoding='utf-8')
    monkeypatch.setenv('BALDR_CONFIG',str(config))
    with pytest.raises(ValueError):
        configure_portable()


def test_frozen_data_cannot_write_into_package(monkeypatch,tmp_path):
    isolate(monkeypatch,tmp_path)
    monkeypatch.setenv('DATA_ROOT',str(tmp_path/'package'/'market'))
    with pytest.raises(ValueError,match='程式包'):
        configure_portable()
@pytest.mark.parametrize('frozen', [False, True])
def test_indicator_log_stays_in_common_output(tmp_path, monkeypatch, frozen):
    from analysis_module.technical_analysis import technical_indicators as indicators
    import logging
    monkeypatch.setattr(sys, 'frozen', frozen, raising=False)
    monkeypatch.setenv('OUTPUT_ROOT', str(tmp_path/'output'))
    monkeypatch.chdir(tmp_path)
    calculator = indicators.TechnicalIndicatorCalculator()
    logger = logging.getLogger(indicators.__name__)
    paths = [Path(handler.baseFilename) for handler in logger.handlers if isinstance(handler, logging.FileHandler)]
    assert paths == [tmp_path/'output/application_state/logs/technical_calculation.log']
    assert not (tmp_path/'technical_calculation.log').exists()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
def test_gui_ml_registry_is_separate_from_nested_market_output(tmp_path, monkeypatch):
    import baldr_launcher
    from ui_qt import main as qt_main
    isolate(monkeypatch, tmp_path)
    monkeypatch.setenv('DATA_ROOT', str(tmp_path/'market'))
    monkeypatch.setenv('OUTPUT_ROOT', str(tmp_path/'market/output'))
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setattr(sys, 'argv', ['baldr.exe'])
    registry_type = qt_main.CurrentRestatedMLRunRegistry
    captured = []
    def inspect_registry(*, application_settings, build_identity, startup_controller):
        captured.append(qt_main.CurrentRestatedMLRunRegistry(
            repository_root=application_settings.ml_registry_repository_root,
        ))
        assert application_settings.runtime_state_root == tmp_path/'market/output/application_state'
        assert build_identity is not None
        assert startup_controller is not None
        return 0
    monkeypatch.setattr(qt_main, 'main', inspect_registry)
    monkeypatch.setattr(qt_main, 'install_crash_diagnostics', lambda: None)
    monkeypatch.setattr(qt_main, 'CurrentRestatedMLRunRegistry', registry_type)
    monkeypatch.setattr(qt_main, 'MainWindow', qt_main.MainWindow)
    assert baldr_launcher.main() == 0
    assert captured[0].repository_root == tmp_path/'local/baldr/research_state'
    assert not captured[0].research_root.is_relative_to(tmp_path/'market')
    assert qt_main.CurrentRestatedMLRunRegistry is registry_type
