import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.qt_support import application, flush
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from agent_team import DEFAULTS
from backend import AccountError, Controller
from locales import set_language, tr
from team_ui import TeamPanel, RemoteTeamView
from themes import DARK


ACCOUNTS = [
    {'name': 'google-test.json', 'label': 'google@example.com', 'provider': 'antigravity',
     'models': ['gemini-3.8-flash-high', 'claude-opus-4-6-thinking']},
    {'name': 'chatgpt-test.json', 'label': 'chatgpt@example.com', 'provider': 'codex',
     'models': ['gpt-6-luna']},
]


class TeamUITests(unittest.TestCase):
    def setUp(self):
        application()
        set_language('en')
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.controller = Controller(proxy_dir=root / 'proxy', data_dir=root / 'data')
        self.controller.key = 'test-management-key'
        self.host = QWidget()
        self.host.controller = self.controller
        self.host.theme = SimpleNamespace(colors=lambda: DARK)
        self.host.display_name = lambda account: account['email']
        self.host.show_notice = Mock()
        self.host.work = lambda operation, done: done(operation())
        self.panel = TeamPanel(self.host)
        QVBoxLayout(self.host).addWidget(self.panel)
        self.host.resize(1100, 850)
        self.host.show()
        self.inventory = patch('team_ui.inventory', return_value=copy.deepcopy(ACCOUNTS))
        self.inventory.start()
        self.remote = patch('team_ui.TeamClient')
        self.remote.start().return_value.request.return_value = {'run': None}
        flush()

    def tearDown(self):
        self.panel.shutdown()
        self.host.close()
        self.host.deleteLater()
        flush()
        self.inventory.stop()
        self.remote.stop()
        self.temp.cleanup()
        set_language('en')

    def click(self, widget):
        self.panel.ensureWidgetVisible(widget)
        flush()
        position = QPoint(8, widget.height() // 2) if widget is self.panel.enabled else widget.rect().center()
        QTest.mouseClick(widget, Qt.LeftButton, pos=position)
        flush()

    def load_roster(self, count=3):
        self.click(self.panel.reload)
        self.panel.count.setValue(count)
        self.click(self.panel.generate)

    def test_edit_generate_add_remove_save_while_disabled_without_model_calls(self):
        p = self.panel
        with patch('team_ui.TeamRun') as run:
            self.assertFalse(p.enabled.isChecked())
            self.load_roster()
            self.assertEqual(p.roster.rowCount(), 3)
            self.assertTrue(p.task.isEnabled())
            self.assertTrue(p.save_button.isEnabled())
            self.assertTrue(p.settings.isEnabled())
            self.assertIn(tr('team_disabled_hint'), p.start_hint.text())
            self.click(p.settings_fold.button)
            self.assertTrue(p.settings.isVisible())
            self.click(p.add)
            self.assertEqual(p.roster.rowCount(), 4)
            p.roster.setCurrentCell(1, 0)
            self.click(p.remove)
            self.assertEqual(p.roster.rowCount(), 3)
            self.click(p.add)
            ids = [row['id'] for row in p.roster_config()]
            self.assertEqual(len(ids), len(set(ids)))
            self.click(p.save_button)
            saved = Controller(proxy_dir=self.controller.proxy_dir, data_dir=self.controller.data_dir)
            self.assertFalse(saved.preferences['agent-team']['enabled'])
            self.assertEqual(len(saved.preferences['agent-team']['participants']), 4)
            self.assertEqual(p.feedback.text(), tr('team_saved'))
            self.assertTrue(p.feedback.isVisible())
            run.assert_not_called()

    def test_explicit_enable_and_task_are_required_then_start_and_stop_work(self):
        p = self.panel
        self.load_roster()
        p.task.setPlainText('Compare the proposals and produce a reviewed answer.')
        self.assertFalse(p.start_button.isEnabled())
        self.assertLess(p.enabled.y(), p.start_button.y())
        self.assertLess(p.start_button.y() - p.enabled.y(), 150)
        self.click(p.enabled)
        self.assertTrue(p.start_button.isEnabled())
        p.task.clear()
        self.assertFalse(p.start_button.isEnabled())
        self.assertEqual(p.start_hint.text(), tr('team_no_task'))
        p.task.setPlainText('A small test task')
        alive = [False]
        run = Mock()
        run.thread.is_alive.side_effect = lambda: alive[0]
        run.start.side_effect = lambda: alive.__setitem__(0, True)
        run.snapshot.return_value = {
            'status': 'working', 'events': [], 'requests': 1, 'config': DEFAULTS,
            'agents': {}, 'result': '',
        }
        with patch('team_ui.TeamRun', return_value=run) as constructor:
            self.click(p.start_button)
            constructor.assert_called_once()
            self.assertTrue(constructor.call_args.args[1]['enabled'])
            run.start.assert_called_once()
            self.assertFalse(p.roster.isEnabled())
            self.assertTrue(p.stop_button.isEnabled())
            self.click(p.stop_button)
            run.cancel.assert_called_once()
            p.tick()
            self.assertFalse(p.stop_button.isEnabled())
            self.assertEqual(p.start_hint.text(), tr('team_stopping'))
            alive[0] = False
            p.tick()
            self.assertTrue(p.start_button.isEnabled())
            self.assertTrue(p.roster.isEnabled())

    def test_validation_and_start_errors_are_visible_beside_the_buttons(self):
        p = self.panel
        self.load_roster()
        p.roster.item(1, 0).setText(p.roster.item(0, 0).text())
        self.click(p.save_button)
        self.assertIn('unique', p.feedback.text())
        self.assertTrue(p.feedback.isVisible())
        self.click(p.generate)
        p.task.setPlainText('Test task')
        self.click(p.enabled)
        with patch('team_ui.TeamRun', side_effect=AccountError('Test provider is unavailable')):
            self.click(p.start_button)
        self.assertEqual(p.feedback.text(), 'Test provider is unavailable')
        self.assertTrue(p.start_button.isEnabled())
        self.assertIsNone(p.run)

    def test_refresh_error_recovers_controls_and_successful_retry_clears_error(self):
        p = self.panel
        self.load_roster()
        p.task.setPlainText('Test task')
        self.click(p.enabled)
        with patch('team_ui.inventory', side_effect=AccountError('Test connection failed')):
            self.click(p.reload)
        self.assertFalse(p.loading)
        self.assertTrue(p.reload.isEnabled())
        self.assertFalse(p.start_button.isEnabled())
        self.assertEqual(p.feedback.text(), 'Test connection failed')
        self.click(p.reload)
        self.assertTrue(p.start_button.isEnabled())
        self.assertEqual(p.load_error, '')

    def test_refresh_without_connection_explains_the_problem(self):
        self.controller.key = None
        self.click(self.panel.reload)
        self.assertEqual(self.panel.feedback.text(), tr('team_not_connected'))
        self.assertFalse(self.panel.loading)

    def test_export_click_writes_result_and_reports_write_failure(self):
        p = self.panel
        self.assertFalse(p.export_button.isEnabled())
        self.assertEqual(p.export_button.toolTip(), tr('team_no_result'))
        p.show_state({'status': 'complete', 'config': DEFAULTS, 'requests': 3,
                      'result': 'Reviewed result', 'agents': {}, 'events': []})
        self.assertTrue(p.export_button.isEnabled())
        output = Path(self.temp.name) / 'result.md'
        with patch('team_ui.QFileDialog.getSaveFileName', return_value=(str(output), 'Markdown (*.md)')):
            self.click(p.export_button)
        self.assertEqual(output.read_text('utf-8'), 'Reviewed result')
        self.assertEqual(p.feedback.text(), tr('team_exported'))
        with patch('team_ui.QFileDialog.getSaveFileName', return_value=(str(output / 'missing.md'), '')):
            self.click(p.export_button)
        self.assertEqual(p.feedback.text(), tr('team_export_error'))

    def test_connect_button_publishes_saved_roster_and_adds_both_invocation_methods(self):
        self.host.integrations = SimpleNamespace(connect_team_clients=Mock(return_value=['claude_desktop']))
        self.load_roster()
        self.click(self.panel.connect_button)
        self.host.integrations.connect_team_clients.assert_called_once()
        self.assertEqual(len(self.controller.preferences['agent-team']['participants']), 3)
        self.assertEqual(self.panel.feedback.text(), tr('team_chat_connected'))

    def test_chat_run_appears_on_board_and_ui_close_does_not_cancel_it(self):
        state = {'id': 'a' * 32, 'source': 'chat', 'status': 'working', 'config': DEFAULTS,
                 'requests': 2, 'events': [], 'agents': {}, 'result': ''}
        with patch('team_ui.TeamClient') as factory:
            factory.return_value.request.return_value = {'run': state}
            self.panel.remote_checked = 0
            self.panel.poll_remote()
            self.assertIsInstance(self.panel.run, RemoteTeamView)
            self.assertTrue(self.panel.active())
            self.panel.tick()
            self.assertTrue(self.panel.stop_button.isEnabled())
            self.assertFalse(self.panel.save_button.isEnabled())
            factory.return_value.request.reset_mock()
            self.panel.shutdown()
            factory.return_value.request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
