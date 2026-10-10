import ast, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from tests.qt_support import application, flush, until
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel, QComboBox, QPushButton, QMessageBox, QSystemTrayIcon
from app import App
from backend import Controller, AccountError
from locales import tr, LANGUAGES, current_language, set_language, display_reason, _strings
from themes import DARK, LIGHT
from integrations import Integrations


class QuotaUITests(unittest.TestCase):
    def setUp(self):
        self.qapp = application()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.controller = Controller(proxy_dir=root/'proxy', data_dir=root/'data')
        self.patches = [patch('app.Controller', return_value=self.controller)]
        self.patches += [patch.object(App, name) for name in ('refresh','fetch_quota','start_activity','queue_policy','poll_gateway_jobs','connection_settings','check_vpn')]
        for p in self.patches:p.start()
        self.window = App()
        self.window.integrations = Integrations(self.controller, home=root/'home', local=root/'local')

    def tearDown(self):
        self.window.closed = True
        self.window.close()
        self.window.deleteLater()
        flush()
        for p in reversed(self.patches):p.stop()
        set_language('en')
        self.temp.cleanup()

    def load_accounts(self):
        items = [{'name':n, 'email':n+'@example.com', 'disabled':False,'unavailable':False} for n in ('a','b','c')]
        now = datetime.now(timezone.utc)
        for item in items:
            self.window.quota_cache[item['name']] = {'data':{'groups':[
                {'kind':kind,'name':kind,'buckets':[
                    {'window':win,'remaining':.7,'reset':(now+timedelta(hours=5 if win=='5h' else 160)).isoformat()}
                    for win in ('5h','weekly')]}
                for kind in ('gemini','claude')]}}
        self.window.loaded(items)
        flush()
        return items

    def test_four_quotas_per_card_and_detail(self):
        self.load_accounts()
        w=self.window
        self.assertEqual(len(w.account_widgets),3)
        for card in w.account_widgets.values():
            self.assertEqual(set(card.quota_rows),{('gemini','5h'),('gemini','weekly'),('claude','5h'),('claude','weekly')})
        self.assertEqual(len(w.detail_quota_widgets),4)
        self.assertAlmostEqual(w.total_remaining,.7)
        w.select_account('b')
        self.assertEqual(w.detail_account,'b')

    def test_worker_runs_in_background_and_delivers_on_gui_thread(self):
        result=[]
        self.window.work(lambda: QThread.currentThread()==self.qapp.thread(),
            lambda value: result.append((value,QThread.currentThread()==self.qapp.thread())), mutation=True)
        self.assertFalse(self.window.add_button.isEnabled())
        self.assertTrue(until(lambda:bool(result)))
        self.assertEqual(result,[(False,True)])
        self.assertFalse(self.window.busy)
        self.assertFalse(self.window._workers)
        self.assertTrue(self.window.add_button.isEnabled())

    def test_worker_failure_is_visible_and_releases_mutation(self):
        def fail():raise AccountError('Account service unavailable')
        self.window.work(fail,lambda _:self.fail('failure callback must not succeed'),mutation=True)
        self.assertTrue(until(lambda:not self.window.busy))
        self.assertIn('Account service unavailable',self.window.notice.text())
        self.assertFalse(self.window._workers)

    def test_language_switch_rebuilds_all_labels_and_preserves_stats_filter(self):
        self.load_accounts()
        w=self.window
        w.view_switch.set(tr('tab_routing_stats'));w.change_view(tr('tab_routing_stats'))
        w.journal_filter.set(tr('stats_filter_errors'))
        for code in LANGUAGES:
            w.lang_combo.setCurrentIndex(w.lang_combo.findData(code));flush()
            self.assertEqual(current_language(),code)
            self.assertEqual(w.windowTitle(),tr('app_title'))
            self.assertIn(tr('heading_saved_accounts'),[label.text() for label in w.findChildren(QLabel)])
            self.assertEqual(w.view_switch.get(),tr('tab_routing_stats'))
            self.assertEqual(w.journal_filter.get(),tr('stats_filter_errors'))
            self.assertEqual(w.view_stack.currentIndex(),1)
            self.assertEqual(len(w.account_widgets),3)
        self.assertEqual(self.controller.preferences['language'],list(LANGUAGES)[-1])

    def test_theme_and_compact_language_choice_survive_restart(self):
        self.load_accounts();w=self.window
        w.toggle_theme();self.assertEqual(w.theme.current,'light')
        self.assertIn(w.theme.color('bg'),w.styleSheet())
        w.toggle_details();self.assertTrue(w.details_collapsed)
        w.lang_combo.setCurrentIndex(w.lang_combo.findData('ru'));flush()
        self.assertTrue(w.details_collapsed);self.assertTrue(w.body_container.isHidden())
        restored=Controller(proxy_dir=self.controller.proxy_dir,data_dir=self.controller.data_dir)
        self.assertEqual(restored.preferences['theme'],'light')
        self.assertEqual(restored.preferences['language'],'ru')
        self.assertTrue(restored.preferences['details-collapsed'])

    def test_compact_delete_targets_clicked_account_and_can_cancel(self):
        items=self.load_accounts();w=self.window;w.toggle_details()
        with patch.object(self.controller,'remove_account') as remove,patch.object(self.controller,'accounts',return_value=[items[0],items[2]]),patch('app.QMessageBox.question',return_value=QMessageBox.No):
            w.account_widgets['b'].remove_button.click();remove.assert_not_called()
        with patch.object(self.controller,'remove_account') as remove,patch.object(self.controller,'accounts',return_value=[items[0],items[2]]),patch('app.QMessageBox.question',return_value=QMessageBox.Yes) as confirm:
            w.account_widgets['b'].remove_button.click()
            self.assertTrue(until(lambda:not w.busy))
            remove.assert_called_once_with('b')
            self.assertIn('b@example.com',confirm.call_args.args[2])
        self.assertEqual(set(w.account_widgets),{'a','c'})
        self.assertNotIn('b',w.quota_cache)
        self.assertEqual(w.selected,'a')

    def test_model_picker_applies_exact_provider_ids(self):
        w=self.window
        choices={'gemini':['gemini-3.1-pro-low','gemini-pro-agent','gemini-3-flash'],'claude':['claude-opus-4-6-thinking']}
        with patch.object(self.controller,'family_model_choices',return_value=choices),patch.object(self.controller,'request',return_value={'oauth-model-alias':{'antigravity':[]}}),patch.object(self.controller,'set_family_models',return_value={'claude-sonnet-4-5':'gemini-pro-agent'}) as apply,patch.object(w.integrations,'apply') as setup:
            w.model_settings()
            selectors=w.model_dialog.findChildren(QComboBox)
            self.assertTrue(until(lambda:len(selectors)==2 and all(s.isEnabled() for s in selectors)))
            selectors[1].setCurrentText('3.1 Pro High')
            button=next(b for b in w.model_dialog.findChildren(QPushButton) if b.text()==tr('btn_apply_models'))
            button.click()
            self.assertTrue(until(lambda:apply.called))
            apply.assert_called_once_with('gemini-pro-agent','claude-opus-4-6-thinking')
            setup.assert_not_called()

    def test_qt_preview_renders_in_both_themes(self):
        self.load_accounts();w=self.window
        w.resize(1120,850);w.show();flush()
        for theme in ('dark','light'):
            if w.theme.current!=theme:w.toggle_theme()
            self.assertTrue(until(lambda:all(r.height() >= r.minimumSizeHint().height() for r in w.detail_quota_widgets.values())))
            image=w.grab().toImage()
            self.assertFalse(image.isNull())
            self.assertEqual(image.width(),w.width())
            Path('build').mkdir(exist_ok=True)
            image.save(str(Path('build')/('pyside-'+theme+'-preview.png')))

    def test_light_theme_is_opaque_and_independent_of_system_palette(self):
        self.load_accounts();w=self.window
        original=QPalette(self.qapp.palette())
        system_dark=QPalette(original)
        system_dark.setColor(QPalette.Window,QColor('black'))
        system_dark.setColor(QPalette.Text,QColor('white'))
        self.qapp.setPalette(system_dark)
        try:
            w.toggle_theme();w.show();flush()
            self.assertFalse(w.testAttribute(Qt.WA_TranslucentBackground))
            self.assertEqual(w.palette().color(QPalette.Window).name(),LIGHT['bg'])
            self.assertEqual(w.palette().color(QPalette.Text).name(),LIGHT['text'])
            self.assertEqual(w.service.palette().color(QPalette.WindowText).name(),LIGHT['green'])
            self.assertEqual(w.grab().toImage().pixelColor(410,3).name(),LIGHT['bg'])
            self.assertNotIn(LIGHT['bg']+'CC',w.styleSheet())
        finally:
            self.qapp.setPalette(original)

    def test_language_switch_keeps_one_tray_and_one_vpn_timer(self):
        w=self.window;tray=w.tray_icon;timer=w._vpn_timer
        for code in LANGUAGES:
            w.lang_combo.setCurrentIndex(w.lang_combo.findData(code));flush()
            self.assertIs(w.tray_icon,tray)
            self.assertIs(w._vpn_timer,timer)
            self.assertEqual(len(w.findChildren(QSystemTrayIcon)),1)
            self.assertTrue(timer.isActive())
            self.assertEqual(w.action_show.text(),tr('tray_show'))

    def test_existing_ranking_is_translated_on_language_switch(self):
        self.load_accounts();w=self.window
        w.policy_rows=[{'name':'a','reason':'Quota available; nearest 5h reset','reset':None}]
        w.policy_group='gemini'
        w.lang_combo.setCurrentIndex(w.lang_combo.findData('ru'));flush()
        self.assertIn(tr('rank_available'),w.policy_label.text())
        self.assertNotIn('Quota available',w.policy_label.text())

    def test_mini_mode_has_usable_width_and_restores_full_window(self):
        self.load_accounts();w=self.window;w.resize(1120,850);w.show();flush()
        size=w.size();w.toggle_mini_mode();flush()
        self.assertTrue(w.details_collapsed);self.assertTrue(w.is_mini)
        self.assertLessEqual(w.width(),420)
        self.assertTrue(w.windowFlags() & Qt.WindowStaysOnTopHint)
        w.lang_combo.setCurrentIndex(w.lang_combo.findData('ru'));flush()
        self.assertEqual(w.btn_mini.text(),tr('btn_full_mode'))
        w.toggle_mini_mode();flush()
        self.assertFalse(w.details_collapsed);self.assertFalse(w.is_mini)
        self.assertFalse(w.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertEqual(w.size(),size)

    def test_cached_quota_is_dimmed_and_does_not_confirm_access(self):
        items=self.load_accounts();w=self.window
        items[1].update(status='error',unavailable=True,access_issue='login')
        w.quota_cache['b'].update(error='The local connection returned error 400.',at=datetime.now(timezone.utc))
        w.draw_account_list();flush()
        card=w.account_widgets['b']
        self.assertIn(tr('account_sign_in_again'),card.status_label.text())
        self.assertIn(tr('account_cached_quota'),card.status_label.text())
        self.assertAlmostEqual(w.quota_groups('b')[0]['buckets'][0]['remaining'],.7)
        self.assertIn(w.theme.color('muted'),card.quota_rows[('gemini','5h')].bar.styleSheet())
        self.assertEqual(w.total_quota_title.text(),tr('quota_5h_data',count=2,total=3))
        w.animate_active_borders()
        self.assertIn(tr('quota_cached_data'),card.toolTip())
        w.select_account('b')
        self.assertIn(tr('quota_cached_data'),w.quota_updated.text())
        w.quota_cache['a']['at']=datetime.now(timezone.utc)-timedelta(minutes=4)
        self.assertTrue(w.quota_is_cached(items[0]))

    def test_stats_name_the_model_with_a_cooldown(self):
        items=self.load_accounts();w=self.window
        items[0]['cooldowns']=[{'model_key':'claude-opus-4-6-thinking','scope':'model',
            'retry_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}]
        set_language('ru');w.render_activity()
        label=w.stats_accounts_layout.itemAt(0).widget().text()
        self.assertIn('Opus',label)
        self.assertIn(tr('account_enabled_status'),label)
        self.assertNotIn(tr('activity_waiting_restricted'),label)

    def test_vpn_warning_does_not_stop_ui_polling_or_local_controls(self):
        w=self.window;w._vpn_state_received(False)
        self.assertFalse(w.vpn_active)
        self.assertFalse(w.vpn_banner.isHidden())
        self.assertTrue(all(timer.isActive() for timer in (w._quota_timer,w._countdown_timer,w._gateway_timer)))
        called=[]
        with patch.object(self.controller,'accounts',return_value=[]):
            w.action(lambda:called.append(True),'ok')
            self.assertTrue(until(lambda:not w.busy))
        self.assertEqual(called,[True])

    def test_all_literal_ui_keys_have_five_translations(self):
        for source in ('app.py','widgets.py'):
            tree=ast.parse(Path(source).read_text('utf-8'))
            keys={n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Name) and n.func.id=='tr' and n.args
                and isinstance(n.args[0],ast.Constant)}
            self.assertFalse(keys-_strings.keys())
            for key in keys:self.assertEqual(set(_strings[key]),set(LANGUAGES))
        for code in LANGUAGES:
            set_language(code)
            self.assertEqual(display_reason('Quota available; nearest 5h reset'),tr('rank_available'))
            self.assertEqual(display_reason('Retry using another account: Google 429: quota exhausted for this model'),
                tr('event_retry_account',reason=tr('event_exhausted')))

    def test_multilingual_previews_and_toolbar_fit(self):
        self.load_accounts();w=self.window
        w.items[1].update(status='error',unavailable=True,access_issue='login')
        w.quota_cache['b']['error']='The local connection returned error 400.'
        w.resize(1120,850);w.show();flush()
        preview=Path('build/ui-fix');preview.mkdir(parents=True,exist_ok=True)
        for code in LANGUAGES:
            w.lang_combo.setCurrentIndex(w.lang_combo.findData(code));flush()
            self.assertEqual(w.width(),1120)
            self.assertGreaterEqual(w.add_button.width(),200)
            for theme in ('dark','light'):
                if w.theme.current!=theme:w.toggle_theme()
                self.assertTrue(until(lambda:all(r.height()>=r.minimumSizeHint().height() for r in w.detail_quota_widgets.values())))
                self.assertTrue(w.grab().save(str(preview/f'{theme}-{code}.png')))


if __name__=='__main__':unittest.main()
