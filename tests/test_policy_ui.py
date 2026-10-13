import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QCheckBox, QPushButton
from tests.qt_support import flush
import tests.test_quota_ui as quota_ui_support
from policy_widgets import ReserveBar, QuotaCircle
from locales import tr


class PolicyUITests(unittest.TestCase):
    setUp = quota_ui_support.QuotaUITests.setUp
    tearDown = quota_ui_support.QuotaUITests.tearDown
    load_accounts = quota_ui_support.QuotaUITests.load_accounts

    def test_priority_moves_existing_cards_and_preserves_quota_tracks(self):
        self.load_accounts()
        w = self.window
        card = w.account_widgets['c']
        track = card.quota_rows[('gemini', '5h')].bar
        card.priority_control.input.setValue(30)
        flush()
        self.assertIs(w.account_widgets['c'], card)
        self.assertIs(w.account_widgets['c'].quota_rows[('gemini', '5h')].bar, track)
        self.assertLess(w.account_list_layout.indexOf(card), w.account_list_layout.indexOf(w.account_widgets['a']))
        self.assertEqual(w.controller.preferences['account-priorities']['c'], 30)
        QTest.mouseClick(card.priority_control.up, Qt.LeftButton)
        self.assertEqual(w.controller.preferences['account-priorities']['c'], 31)
        QTest.mouseClick(card.priority_control.down, Qt.LeftButton)
        self.assertEqual(w.controller.preferences['account-priorities']['c'], 30)
        self.assertEqual(w.controller.preferences['mode'], 'pool')
        card.priority_control.input.selectAll()
        QTest.keyClicks(card.priority_control.input, '120')
        QTest.keyClick(card.priority_control.input, Qt.Key_Return)
        self.assertEqual(w.controller.preferences['account-priorities']['c'], 120)
        self.assertEqual(card.priority_control.input.text(), '120')
        self.assertGreater(card.priority_control.input.width() - 10,
                           card.priority_control.input.fontMetrics().horizontalAdvance('120'))

    def test_real_marker_drag_commits_once_and_persists_separate_window(self):
        self.load_accounts()
        w = self.window
        w.show(); flush()
        bar = w.account_widgets['a'].quota_rows[('gemini', '5h')].bar
        committed = []
        bar.reserve_changed.connect(committed.append)
        start = QPoint(5, bar.height() // 2)
        target = QPoint(round(bar.track().left() + bar.track().width() * .2), bar.height() // 2)
        QTest.mousePress(bar, Qt.LeftButton, pos=start)
        QTest.mouseMove(bar, target)
        self.assertEqual(committed, [])
        QTest.mouseRelease(bar, Qt.LeftButton, pos=target)
        flush()
        self.assertEqual(committed, [20])
        self.assertEqual(w.controller.preferences['quota-floors']['a']['gemini']['5h'], 20)
        self.assertEqual(w.detail_quota_widgets[('gemini', '5h')].bar.floor(), 20)
        self.assertEqual(w.account_widgets['a'].quota_rows[('claude', '5h')].bar.floor(), 0)
        QTest.keyClick(bar, Qt.Key_End)
        self.assertEqual(bar.floor(), 100)
        QTest.keyClick(bar, Qt.Key_Home)
        self.assertEqual(bar.floor(), 0)

    def test_visibility_and_fold_controls_keep_footer_and_connections(self):
        self.load_accounts()
        w = self.window
        before = dict(w.controller.preferences)
        w.google_fold.toggle(); flush()
        self.assertTrue(w.account_scroll.isHidden())
        self.assertFalse(w.sidebar_spacer.isHidden())
        self.assertEqual(len(w.google_fold.circles), 4)
        self.assertAlmostEqual(w.google_fold.circles[0].fraction, .7)
        def edit(dialog):
            for p in ('google', 'api', 'codex', 'claude'):
                dialog.findChild(QCheckBox, 'serviceVisibility_' + p).setChecked(False)
            dialog.findChild(QPushButton, 'weeklyThresholdSave').click()
            return QDialog.Accepted
        with patch.object(QDialog, 'exec', edit): w.quota_display_settings()
        self.assertEqual(w.view_stack.currentIndex(), 1)
        self.assertFalse(w.display_settings_button.isHidden())
        self.assertEqual(w.controller.preferences['mode'], before['mode'])
        w.toggle_mini_mode(); w.show(); flush()
        self.assertGreater(w.btn_mini.mapTo(w.sidebar, QPoint()).y(), w.sidebar.height() - 70)
        self.assertEqual(len(w.items), 3)

    def test_subscription_cards_survive_usage_refresh_and_language_switch(self):
        self.load_accounts()
        w = self.window
        row = {'name': 'test-codex', 'status': 'active', 'quota': {'windows': [
            {'label': '5h', 'remaining': 70, 'reset_at': 2000000000},
            {'label': '1w', 'remaining': 80, 'reset_at': 2100000000}]}}
        w.chatgpt_accounts = [row]
        w.render_chatgpt_accounts(); flush()
        card = w.chatgpt_cards.cards['test-codex']['card']
        track = w.chatgpt_cards.cards['test-codex']['tracks']['5h'][1]
        row['quota']['windows'][0]['remaining'] = 60
        w.render_chatgpt_accounts(); flush()
        self.assertIs(w.chatgpt_cards.cards['test-codex']['card'], card)
        self.assertIs(w.chatgpt_cards.cards['test-codex']['tracks']['5h'][1], track)
        w.view_stack.setCurrentIndex(3); w.resize(1000, 720); w.show(); flush()
        scroll = w.view_stack.currentWidget()
        self.assertLessEqual(scroll.widget().width(), scroll.viewport().width())
        w.chatgpt_cards.header.toggle()
        self.assertTrue(w.chatgpt_cards.body.isHidden())
        w.lang_combo.setCurrentIndex(w.lang_combo.findData('ru')); flush()
        self.assertTrue(w.chatgpt_cards.body.isHidden())
        self.assertEqual(w.display_settings_button.toolTip(), tr('display_settings'))

    def test_unknown_circle_differs_from_exhausted_quota(self):
        circle = QuotaCircle('5h')
        circle.set_value(None)
        unknown = circle.grab().toImage()
        circle.set_value(0)
        exhausted = circle.grab().toImage()
        self.assertNotEqual(unknown, exhausted)
        circle.deleteLater()
