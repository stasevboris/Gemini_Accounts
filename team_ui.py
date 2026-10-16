"""User-configurable team roster, permissions, task board and run history."""
import copy
import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from backend import AccountError, dpapi
from agent_team import DEFAULTS, LIMITS, TeamRun, inventory, validate
from locales import tr
from policy_widgets import FoldHeader
from team_service import TeamClient


class RemoteTeamView:
    """Display a gateway-owned run without moving its worker into the UI process."""
    def __init__(self, host, state):
        self.host, self.state = host, state
        self.id = state['id']
        self.thread = self

    def is_alive(self):
        return not self.state.get('finished')

    def snapshot(self):
        return copy.deepcopy(self.state)

    def cancel(self):
        self.host.work(lambda: TeamClient(self.host.controller).request('cancel', {'id': self.id}),
                       lambda result: setattr(self, 'state', result['run']))


class TeamPanel(QScrollArea):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.accounts = []
        self.run = None
        self.loading = False
        self.load_error = ''
        self.stopping = False
        self.remote_loading = False
        self.remote_checked = 0
        self.last_remote_id = None
        self.rendered = None
        self.config = {**copy.deepcopy(DEFAULTS), **copy.deepcopy(host.controller.preferences.get('agent-team', {}))}
        self.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.title = QLabel()
        self.title.setFont(QFont('Segoe UI', 22, QFont.Bold))
        layout.addWidget(self.title)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setProperty('class', 'muted')
        layout.addWidget(self.note)
        self.enabled = QCheckBox()
        self.enabled.setChecked(self.config['enabled'])
        self.enabled.toggled.connect(self.enable_changed)
        self.settings = QWidget()
        self.settings_fold = FoldHeader(tr('team_settings'), [], True)
        self.settings_fold.toggled.connect(lambda collapsed: self.settings.setVisible(not collapsed))
        layout.addWidget(self.settings_fold)
        form = QFormLayout(self.settings)
        self.mode = QComboBox()
        self.mode.addItem('', 'general')
        self.mode.addItem('', 'code')
        self.mode.setCurrentIndex(self.mode.findData(self.config['mode']))
        self.mode_label = QLabel()
        form.addRow(self.mode_label, self.mode)
        folder = QWidget()
        folder_layout = QHBoxLayout(folder)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self.workspace = QLineEdit(self.config['workspace'])
        self.browse = QPushButton('…')
        self.browse.clicked.connect(self.choose_folder)
        folder_layout.addWidget(self.workspace, 1)
        folder_layout.addWidget(self.browse)
        self.workspace_label = QLabel()
        form.addRow(self.workspace_label, folder)
        self.spins, self.spin_labels = {}, {}
        for key, (minimum, maximum) in LIMITS.items():
            spin = QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setValue(self.config[key])
            label = QLabel()
            self.spins[key], self.spin_labels[key] = spin, label
            form.addRow(label, spin)
        self.web, self.write, self.commands = QCheckBox(), QCheckBox(), QCheckBox()
        for key, control in [('web', self.web), ('write', self.write), ('commands', self.commands)]:
            control.setChecked(self.config[key])
            form.addRow(control)
        self.permissions_note = QLabel()
        self.permissions_note.setWordWrap(True)
        self.permissions_note.setProperty('class', 'muted')
        form.addRow(self.permissions_note)
        layout.addWidget(self.settings)
        self.settings.hide()
        self.task = QTextEdit()
        self.task.setMinimumHeight(100)
        self.task.setMaximumHeight(180)
        layout.addWidget(self.task)
        layout.addWidget(self.enabled)
        chat_controls = QHBoxLayout()
        self.connect_button = QPushButton()
        self.connect_button.clicked.connect(self.connect_chat)
        self.chat_hint = QLabel()
        self.chat_hint.setWordWrap(True)
        self.chat_hint.setProperty('class', 'muted')
        chat_controls.addWidget(self.connect_button)
        chat_controls.addWidget(self.chat_hint, 1)
        layout.addLayout(chat_controls)
        self.start_hint = QLabel()
        self.start_hint.setWordWrap(True)
        self.start_hint.setProperty('class', 'muted')
        layout.addWidget(self.start_hint)
        actions = QHBoxLayout()
        self.save_button, self.start_button, self.stop_button, self.export_button = (QPushButton() for _ in range(4))
        self.save_button.clicked.connect(self.save_settings)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.export_button.clicked.connect(self.export_result)
        for button in (self.save_button, self.start_button, self.stop_button, self.export_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.PlainText)
        self.feedback.hide()
        layout.addWidget(self.feedback)
        controls = QHBoxLayout()
        self.reload = QPushButton()
        self.reload.clicked.connect(self.refresh)
        self.count = QSpinBox()
        self.count.setRange(1, 100)
        self.count.setValue(8)
        self.generate = QPushButton()
        self.generate.clicked.connect(self.generate_roster)
        self.add = QPushButton('+')
        self.add.clicked.connect(lambda: self.add_row())
        self.remove = QPushButton('−')
        self.remove.clicked.connect(self.remove_row)
        controls.addWidget(self.reload)
        controls.addWidget(self.count)
        controls.addWidget(self.generate)
        controls.addWidget(self.add)
        controls.addWidget(self.remove)
        layout.addLayout(controls)
        self.roster = QTableWidget(0, 5)
        self.roster.setMinimumHeight(230)
        self.roster.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.roster.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.roster.horizontalHeader().setStretchLastSection(True)
        self.roster.setColumnWidth(0, 80)
        self.roster.setColumnWidth(1, 220)
        self.roster.setColumnWidth(2, 190)
        self.roster.setColumnWidth(3, 130)
        layout.addWidget(self.roster)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.board = QTableWidget(0, 5)
        self.board.setMinimumHeight(180)
        self.board.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.board.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.board)
        self.history = QComboBox()
        self.history.currentIndexChanged.connect(self.show_history)
        layout.addWidget(self.history)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(220)
        layout.addWidget(self.result)
        self.journal = QTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumHeight(160)
        layout.addWidget(self.journal)
        layout.addStretch()
        self.setWidget(content)
        self.task.textChanged.connect(self.update_enabled)
        self.roster.itemSelectionChanged.connect(self.update_enabled)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(700)
        self.reload_history()
        self.render()
        self.update_enabled()

    def render(self):
        self.title.setText(tr('team_title'))
        self.note.setText(tr('team_note'))
        self.settings_fold.set_title(tr('team_settings'))
        self.settings_fold.set_theme(self.host.theme.colors())
        self.enabled.setText(tr('team_enable'))
        self.connect_button.setText(tr('team_connect_chat'))
        self.chat_hint.setText(tr('team_chat_hint'))
        self.mode.setItemText(0, tr('team_general'))
        self.mode.setItemText(1, tr('team_code'))
        self.mode_label.setText(tr('team_mode'))
        self.workspace_label.setText(tr('team_workspace'))
        for key, label in self.spin_labels.items():
            label.setText(tr('team_' + key))
        for key, button in [('web', self.web), ('write', self.write), ('commands', self.commands),
                            ('refresh', self.reload), ('generate', self.generate), ('save', self.save_button),
                            ('start', self.start_button), ('stop', self.stop_button), ('export', self.export_button)]:
            button.setText(tr('team_' + key))
        self.permissions_note.setText(tr('team_permissions'))
        self.roster.setHorizontalHeaderLabels([tr('team_agent'), tr('team_account'), tr('team_model'), tr('team_role'), tr('team_instructions')])
        self.board.setHorizontalHeaderLabels([tr('team_agent'), tr('team_status'), tr('team_subtask'), tr('team_review'), tr('team_feedback')])
        self.task.setPlaceholderText(tr('team_task'))
        self.add.setToolTip(tr('team_add'))
        self.count.setToolTip(tr('team_count'))
        self.journal.setPlaceholderText(tr('team_journal'))
        for row in range(self.roster.rowCount()):
            roles = self.roster.cellWidget(row, 3)
            for index, key in enumerate(('coordinator', 'worker', 'reviewer')):
                roles.setItemText(index, tr('team_' + key))
        self.tick()

    def active(self):
        return bool(self.run and self.run.thread and self.run.thread.is_alive())

    def update_enabled(self):
        active = self.active()
        enabled = self.enabled.isChecked()
        self.enabled.setEnabled(not active)
        self.connect_button.setEnabled(not active)
        # Preparing a team must work before opting in to provider requests.
        for widget in (self.settings, self.task, self.save_button):
            widget.setEnabled(not active)
        editable = not active and not self.loading
        self.roster.setEnabled(editable)
        self.count.setEnabled(editable)
        for widget in (self.generate, self.add):
            widget.setEnabled(editable and bool(self.accounts))
        self.remove.setEnabled(editable and self.roster.currentRow() >= 0)
        self.remove.setToolTip(tr('team_remove' if self.roster.currentRow() >= 0 else 'team_select_row'))
        self.reload.setEnabled(not active and not self.loading)
        if active:
            reason = 'stopping' if self.stopping else 'running'
        elif self.loading:
            reason = 'loading'
        elif self.load_error:
            reason = 'reload_needed'
        elif not enabled:
            reason = 'disabled_hint'
        elif not self.accounts:
            reason = 'no_accounts'
        elif not self.roster.rowCount():
            reason = 'no_roster'
        elif not self.task.toPlainText().strip():
            reason = 'no_task'
        else:
            reason = 'ready_hint'
        hint = tr('team_' + reason)
        self.start_hint.setText(hint)
        self.start_button.setToolTip(hint)
        self.start_button.setEnabled(reason == 'ready_hint')
        self.stop_button.setEnabled(active and not self.stopping)
        self.stop_button.setToolTip(tr('team_stop' if active else 'team_no_run'))
        self.export_button.setEnabled(bool(self.result.toPlainText()))
        self.export_button.setToolTip(tr('team_export' if self.result.toPlainText() else 'team_no_result'))
        self.history.setEnabled(not active)

    def notify(self, text, style='green'):
        self.feedback.setText(text)
        self.feedback.setProperty('class', style)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)
        self.feedback.show()
        self.host.show_notice(text, style)

    def enable_changed(self, enabled):
        self.host.controller.preferences.setdefault('agent-team', {})['enabled'] = enabled
        self.host.controller.save()
        self.update_enabled()
        if enabled and not self.accounts:
            self.refresh()

    def choose_folder(self):
        value = QFileDialog.getExistingDirectory(self, tr('team_workspace'), self.workspace.text())
        if value:
            self.workspace.setText(value)

    def connect_chat(self):
        if not self.save_settings():
            return
        self.connect_button.setEnabled(False)
        def done(_):
            self.notify(tr('team_chat_connected'))
            self.update_enabled()
        self.host.work(self.host.integrations.connect_team_clients, done)

    def poll_remote(self):
        if (not self.isVisible() or self.remote_loading or not self.host.controller.key
                or time.monotonic() - self.remote_checked < 1.5
                or self.run is not None and not isinstance(self.run, RemoteTeamView) and self.active()):
            return
        self.remote_loading = True
        self.remote_checked = time.monotonic()
        def fetch():
            try:
                return TeamClient(self.host.controller).request('current').get('run')
            except (AccountError, OSError):
                return None
        def done(state):
            self.remote_loading = False
            if not state:
                return
            if self.run is not None and not isinstance(self.run, RemoteTeamView) and self.active():
                return
            if isinstance(self.run, RemoteTeamView) and self.run.id == state['id']:
                self.run.state = state
            elif not state.get('finished') or state.get('source') in ('chat', 'mcp') and state['id'] != self.last_remote_id:
                self.run = RemoteTeamView(self.host, state)
                self.rendered = None
                self.stopping = False
                self.last_remote_id = state['id']
            self.update_enabled()
        self.host.work(fetch, done)

    def refresh(self):
        if self.loading or self.active():
            return
        if not self.host.controller.key:
            self.notify(tr('team_not_connected'), 'warning')
            return
        self.loading = True
        self.update_enabled()
        def done(result):
            self.loading = False
            rows, self.load_error = result
            if self.load_error:
                self.notify(self.load_error, 'warning')
                self.update_enabled()
                return
            self.accounts = rows
            saved = self.roster_config() if self.roster.rowCount() else self.config['participants']
            self.roster.setRowCount(0)
            for person in saved:
                self.add_row(person)
            if not saved and rows:
                self.generate_roster()
            self.update_enabled()
            self.notify(tr('team_loaded', count=len(rows)))
        def load():
            try:
                return inventory(self.host.controller), ''
            except (AccountError, OSError, ValueError) as error:
                return None, str(error) if isinstance(error, AccountError) else tr('action_generic_error')
        self.host.work(load, done)

    def add_row(self, person=None):
        if not self.accounts or self.roster.rowCount() >= 100:
            return
        row = self.roster.rowCount()
        self.roster.insertRow(row)
        person = person or {}
        used = {self.roster.item(index, 0).text() for index in range(row)}
        number = next(index for index in range(1, 102) if 'agent-' + str(index) not in used)
        self.roster.setItem(row, 0, QTableWidgetItem(person.get('id', 'agent-' + str(number))))
        accounts = QComboBox()
        for account in self.accounts:
            label = self.host.display_name({'name': account['name'], 'email': account['label']})
            provider = {'antigravity': 'Google', 'codex': 'ChatGPT', 'claude': 'Claude'}.get(account['provider'], account['provider'])
            accounts.addItem(provider + ' · ' + label, account['name'])
        index = accounts.findData(person.get('account'))
        accounts.setCurrentIndex(index if index >= 0 else row % len(self.accounts))
        if person.get('account') and index < 0:
            accounts.addItem(tr('team_account_missing'), person['account'])
            accounts.setCurrentIndex(accounts.count() - 1)
        models = QComboBox()
        roles = QComboBox()
        for key in ('coordinator', 'worker', 'reviewer'):
            roles.addItem(tr('team_' + key), key)
        roles.setCurrentIndex(max(0, roles.findData(person.get('role', 'coordinator' if row == 0 else 'worker'))))
        self.roster.setCellWidget(row, 1, accounts)
        self.roster.setCellWidget(row, 2, models)
        self.roster.setCellWidget(row, 3, roles)
        self.roster.setItem(row, 4, QTableWidgetItem(person.get('instructions', '')))
        def populate():
            account = next((a for a in self.accounts if a['name'] == accounts.currentData()), None)
            models.clear()
            if account:
                models.addItems(account['models'])
                preferred = next((m for m in ('gpt-6-luna', 'gemini-3.8-flash-high', 'gpt-5.6-luna') if m in account['models']), account['models'][0])
                models.setCurrentText(preferred)
        accounts.currentIndexChanged.connect(populate)
        populate()
        if person.get('model'):
            if models.findText(person['model']) < 0:
                models.addItem(person['model'])
            models.setCurrentText(person['model'])
        self.roster.setCurrentCell(row, 0)
        self.update_enabled()

    def remove_row(self):
        row = self.roster.currentRow()
        if row >= 0:
            self.roster.removeRow(row)
        self.update_enabled()

    def generate_roster(self):
        if not self.accounts:
            return
        self.roster.setRowCount(0)
        for _ in range(self.count.value()):
            self.add_row()
        minimum_calls = 2 + max(1, self.count.value() - 1) * (1 + self.spins['review_rounds'].value())
        self.spins['max_requests'].setValue(max(self.spins['max_requests'].value(), minimum_calls))
        if self.count.value() > 30:
            self.spins['output_tokens'].setValue(max(8192, self.spins['output_tokens'].value()))

    def roster_config(self):
        result = []
        for row in range(self.roster.rowCount()):
            name = self.roster.cellWidget(row, 1).currentData()
            account = next((a for a in self.accounts if a['name'] == name), {})
            result.append({'id': self.roster.item(row, 0).text().strip(), 'account': name or '',
                           'provider': account.get('provider', ''), 'model': self.roster.cellWidget(row, 2).currentText(),
                           'role': self.roster.cellWidget(row, 3).currentData(),
                           'instructions': self.roster.item(row, 4).text()})
        return result

    def read_config(self):
        return {'enabled': self.enabled.isChecked(), 'mode': self.mode.currentData(),
                'workspace': self.workspace.text().strip(), 'web': self.web.isChecked(),
                'write': self.write.isChecked(), 'commands': self.commands.isChecked(),
                **{key: spin.value() for key, spin in self.spins.items()}, 'participants': self.roster_config()}

    def save_settings(self):
        try:
            config = validate(self.read_config())
        except AccountError as error:
            self.notify(str(error), 'warning')
            return False
        self.config = config
        self.host.controller.preferences['agent-team'] = copy.deepcopy(config)
        self.host.controller.save()
        self.notify(tr('team_saved'))
        return True

    def start(self):
        self.update_enabled()
        if not self.start_button.isEnabled():
            self.notify(self.start_hint.text(), 'warning')
            return
        if not self.save_settings():
            return
        # Account inventory is local metadata; stale/deleted/model-mismatched rows
        # cannot silently fall through to a different account.
        for person in self.config['participants']:
            account = next((a for a in self.accounts if a['name'] == person['account']), None)
            if not account or person['model'] not in account['models']:
                self.notify(tr('team_account_missing'), 'warning')
                return
        try:
            run = TeamRun(self.host.controller, self.config, self.task.toPlainText())
            run.start()
            self.run = run
            self.stopping = False
            self.notify(tr('team_running'))
        except AccountError as error:
            self.notify(str(error), 'warning')
        self.rendered = None
        self.update_enabled()

    def stop(self):
        if self.active() and not self.stopping:
            self.stopping = True
            self.run.cancel()
            self.notify(tr('team_stopping'))
            self.update_enabled()

    def tick(self):
        if self.run:
            state = self.run.snapshot()
            signature = (state['status'], len(state['events']), state['requests'], state.get('finished'))
            if signature != self.rendered:
                self.show_state(state)
                self.rendered = signature
                if state.get('finished'):
                    self.reload_history()
        self.update_enabled()
        self.poll_remote()

    def show_state(self, state):
        self.summary.setText(tr('team_summary', status=tr('team_state_' + state['status']),
            calls=state['requests'], limit=state['config']['max_requests'],
            tokens=state.get('input_tokens', 0) + state.get('output_tokens', 0)))
        self.board.setRowCount(len(state['agents']))
        for row, (ident, data) in enumerate(state['agents'].items()):
            values = (ident, tr('team_state_' + data['status']), data['task'],
                      tr('team_approved') if data['approved'] else tr('team_pending'), data['feedback'])
            for column, value in enumerate(values):
                self.board.setItem(row, column, QTableWidgetItem(str(value)))
        result = state.get('result') or '\n\n'.join(ident + '\n' + data['result'] for ident, data in state['agents'].items() if data['result'])
        if state.get('error'):
            result += '\n\n' + state['error']
        if state.get('route_restore_error'):
            result += '\n\n' + tr('team_restore_error')
        if not result.strip() and state.get('finished'):
            result = '\n\n'.join(ident + '\n' + data['result'] for ident, data in state['agents'].items() if data['result'])
        self.result.setPlainText(result)
        self.journal.setPlainText('\n'.join(time.strftime('%H:%M:%S', time.localtime(e['time'])) + ' · '
            + (e.get('agent') or 'team') + ' · ' + e['text'] for e in state.get('events', [])[-200:]))
        self.update_enabled()

    def reload_history(self):
        selected = self.history.currentData()
        self.history.blockSignals(True)
        self.history.clear()
        self.history.addItem(tr('team_history'), '')
        paths = sorted((self.host.controller.data_dir / 'team-runs').glob('*.dpapi'), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
        for path in paths:
            self.history.addItem(time.strftime('%d.%m %H:%M', time.localtime(path.stat().st_mtime)) + ' · ' + path.stem[:8], path.name)
        self.history.setCurrentIndex(max(0, self.history.findData(selected)))
        self.history.blockSignals(False)

    def show_history(self):
        name = self.history.currentData()
        if not name or self.active() or Path(name).name != name:
            return
        try:
            path = self.host.controller.data_dir / 'team-runs' / name
            state = json.loads(dpapi(path.read_bytes(), decrypt=True))
            if not state.get('finished'):
                state.update(status='interrupted', error=tr('team_interrupted'))
            self.show_state(state)
        except (OSError, ValueError, AccountError):
            self.notify(tr('team_history_error'), 'warning')

    def export_result(self):
        name, _ = QFileDialog.getSaveFileName(self, tr('team_export'), 'team-result.md', 'Markdown (*.md)')
        if name:
            try:
                Path(name).write_text(self.result.toPlainText(), encoding='utf-8')
            except OSError:
                self.notify(tr('team_export_error'), 'warning')
            else:
                self.notify(tr('team_exported'))

    def shutdown(self):
        self.timer.stop()
        if self.run is not None and not isinstance(self.run, RemoteTeamView):
            self.stop()
