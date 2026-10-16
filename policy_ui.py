"""Account policy and display controls adapted to the retained Qt interface."""
from datetime import datetime, timezone
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
from locales import tr
from account_status import account_status, safe_detail
from quota_limits import account_priority, quota_floor, blocked_families, oauth_quota_groups, oauth_window_key, sync_quota_limits
from policy_widgets import PriorityControl, ReserveBar, FoldHeader, ActionGrid


class PolicyControlsMixin:
    def set_policy_controls_enabled(self, enabled):
        for widget in self.findChildren(PriorityControl) + self.findChildren(ReserveBar):
            widget.setEnabled(enabled)

    def service_visible(self, provider):
        values = self.controller.preferences.get('service-visibility', {})
        return not isinstance(values, dict) or values.get(provider, True) is not False

    def build_provider_controls(self):
        header = self.theme_button.parentWidget().layout()
        self.display_settings_button = QPushButton('⚙')
        self.display_settings_button.setProperty('flat', True)
        self.display_settings_button.setFixedSize(28, 26)
        self.display_settings_button.setToolTip(tr('display_settings'))
        self.display_settings_button.clicked.connect(self.quota_display_settings)
        header.addWidget(self.display_settings_button)
        layout = self.sidebar.layout()
        self.google_fold = FoldHeader(tr('google_accounts_count', count=len(self.items)), ['G5h', 'G1w', 'C5h', 'C1w'],
                                      self.controller.preferences.get('google-accounts-collapsed', False))
        self.google_fold.setContentsMargins(12, 0, 12, 0)
        self.google_fold.toggled.connect(lambda value: self.set_section_collapsed('google-accounts-collapsed', value))
        layout.insertWidget(layout.indexOf(self.account_scroll), self.google_fold)
        self.sidebar_spacer = QWidget()
        layout.insertWidget(layout.indexOf(self.account_scroll) + 1, self.sidebar_spacer, 1)
        index = layout.indexOf(self.total_quota_frame)
        layout.removeWidget(self.total_quota_frame)
        layout.removeWidget(self.total_weekly_frame)
        self.google_total_content = QWidget()
        totals = QVBoxLayout(self.google_total_content)
        totals.setContentsMargins(0, 0, 0, 0)
        totals.setSpacing(0)
        totals.addWidget(self.total_quota_frame)
        totals.addWidget(self.total_weekly_frame)
        self.google_total_fold = FoldHeader(tr('google_pool_quotas'), ['5h', '1w'],
                                            self.controller.preferences.get('google-pool-collapsed', False))
        self.google_total_fold.setContentsMargins(14, 0, 14, 0)
        self.google_total_fold.toggled.connect(lambda value: self.set_section_collapsed('google-pool-collapsed', value))
        layout.insertWidget(index, self.google_total_fold)
        layout.insertWidget(index + 1, self.google_total_content)
        self.apply_service_visibility()
        self.update_policy_summaries()

    def set_section_collapsed(self, key, value):
        self.controller.preferences[key] = bool(value)
        self.controller.save()
        self.apply_service_visibility()

    def apply_service_visibility(self):
        if not hasattr(self, 'google_fold'):
            return
        google = self.service_visible('google')
        self.google_fold.setVisible(google)
        self.add_button.setVisible(google)
        self.models_button.setVisible(google)
        self.account_scroll.setVisible(google and not self.google_fold.collapsed)
        self.sidebar_spacer.setVisible(not google or self.google_fold.collapsed)
        self.google_total_fold.setVisible(google)
        self.google_total_content.setVisible(google and not self.google_total_fold.collapsed)
        self.mode_frame.setVisible(google)
        visibility = [google, True, self.service_visible('api'), self.service_visible('codex'),
                      self.service_visible('claude'), True]
        for button, visible in zip(self.view_switch._buttons.values(), visibility):
            button.setVisible(visible)
        index = self.view_stack.currentIndex()
        if not visibility[index]:
            next_index = visibility.index(True)
            label = list(self.view_switch._buttons)[next_index]
            self.view_switch.set(label)
            self.change_view(label)

    def update_policy_summaries(self):
        if not hasattr(self, 'google_fold'):
            return
        self.google_fold.set_title(tr('google_accounts_count', count=len(self.items)))
        self.google_fold.set_theme(self.theme.colors())
        self.google_total_fold.set_theme(self.theme.colors())
        values = []
        for kind, window in [('gemini', '5h'), ('gemini', 'weekly'), ('claude', '5h'), ('claude', 'weekly')]:
            measured = []
            for account in self.items:
                if account.get('disabled') or self.quota_is_cached(account):
                    continue
                group = next((g for g in self.quota_groups(account['name']) if g['kind'] == kind), {})
                value = next((b.get('remaining') for b in group.get('buckets', []) if b['window'] == window), None)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
                    measured.append(value)
            values.append(sum(measured) / len(measured) if measured else None)
        self.google_fold.set_values(values)
        self.google_total_fold.set_values([self.total_remaining, self.total_weekly_remaining])

    def configure_priority_control(self, control, name, provider):
        control.setEnabled(not self.busy)
        control.set_value(account_priority(self.controller.preferences, name))
        control.changed.connect(lambda value: self.set_account_priority(name, provider, value))

    def set_account_priority(self, name, provider, value):
        if self.busy:
            return
        self.controller.preferences.setdefault('account-priorities', {})[name] = value
        self.controller.save()
        if provider == 'google':
            self.policy_rows = []
            self.draw_account_list()
            self.queue_policy()
        elif provider == 'codex':
            self.render_chatgpt_accounts()
            self.refresh_chatgpt_accounts(force=True)
        else:
            self.claude_accounts_panel.render()
            self.claude_accounts_panel.refresh(force=True)

    def bind_reserve_bar(self, bar, name, provider, group, window):
        bar.setEnabled(not self.busy)
        if not window:
            return
        bar.set_floor(quota_floor(self.controller.preferences, name, group, window))
        bar.set_theme(self.theme.colors())
        bar.reserve_changed.connect(lambda value: self.set_quota_reserve(name, provider, group, window, value))

    def set_quota_reserve(self, name, provider, group, window, value):
        if self.busy:
            return
        self.controller.preferences.setdefault('quota-floors', {}).setdefault(name, {}).setdefault(group, {})[window] = value
        self.controller.save()
        if provider == 'google':
            account = next((a for a in self.items if a['name'] == name), None)
            groups = self.quota_groups(name)
            cached = self.quota_cache.get(name, {})
            at = cached.get('at')
            if account and (self.quota_is_cached(account) or not isinstance(at, datetime)
                            or (datetime.now(timezone.utc) - at).total_seconds() > 180):
                groups = []
        else:
            rows = self.chatgpt_accounts if provider == 'codex' else self.claude_accounts_panel.rows
            account = next((a for a in rows if a['name'] == name), None)
            groups = oauth_quota_groups((account or {}).get('quota') or {}, provider)
        def done(_):
            if provider == 'google':
                self.draw_account_list()
                if self.selected == name and hasattr(self, 'quota_updated'):
                    self.update_detail_quota()
                self.policy_rows = []
                self.queue_policy()
                self.fetch_quota(name)
            elif provider == 'codex':
                self.refresh_chatgpt_accounts(force=True)
            else:
                self.claude_accounts_panel.refresh(force=True)
            self.show_notice(tr('quota_reserve_saved', percent=value))
        if account and self.controller.key:
            self.work(lambda: sync_quota_limits(self.controller, account, groups), done, mutation=True)
        else:
            done(None)


class SubscriptionCards(QWidget):
    """Reuse each provider account card while values change."""
    def __init__(self, host, provider, actions, parent=None, quota_labels=('5h', '1w')):
        super().__init__(parent)
        self.host, self.provider, self.actions = host, provider, actions
        self.show_quota = bool(quota_labels)
        self.cards = {}
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.header = FoldHeader('', list(quota_labels), host.controller.preferences.get(provider + '-accounts-collapsed', False))
        self.header.toggled.connect(self.collapse)
        self.layout_.addWidget(self.header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.layout_.addWidget(self.body)
        self.empty = QLabel()
        self.body_layout.addWidget(self.empty)
        self.body.setVisible(not self.header.collapsed)

    def collapse(self, value):
        self.host.controller.preferences[self.provider + '-accounts-collapsed'] = value
        self.host.controller.save()
        self.body.setVisible(not value)

    def render(self, rows):
        host = self.host
        self.header.set_theme(host.theme.colors())
        title = {'codex': 'ChatGPT', 'claude': 'Claude'}.get(self.provider, self.provider.title())
        self.header.set_title(title + f' · {len(rows)}')
        pooled = []
        for label in ('5h', '1w') if self.show_quota else ():
            values = [w['remaining'] / 100 for a in rows if not a.get('disabled') for w in (a.get('quota') or {}).get('windows', [])
                      if w.get('label') == label and isinstance(w.get('remaining'), (int, float))]
            pooled.append(sum(values) / len(values) if values else None)
        self.header.set_values(pooled)
        names = {a['name'] for a in rows}
        for name in list(self.cards):
            if name not in names:
                widget = self.cards.pop(name)['card']
                widget.hide(); widget.deleteLater()
        empty_key = {'codex': 'chatgpt_empty', 'claude': 'claude_empty'}.get(self.provider, 'claude_empty')
        self.empty.setText(tr(empty_key))
        self.empty.setVisible(not rows)
        def order(account):
            quota = account.get('quota') or {}
            state, severity, _ = account_status(account)
            unavailable = account.get('disabled') or quota.get('reserved') or state in ('Limit exhausted', 'Paused') or severity == 'error'
            return bool(unavailable), -account_priority(host.controller.preferences, account['name']), account['name']
        for index, account in enumerate(sorted(rows, key=order)):
            name = account['name']
            quota = account.get('quota') or {}
            signature = tuple(w.get('label') for w in quota.get('windows', [])), bool(quota.get('reset_options'))
            item = self.cards.get(name)
            if item and item['structure'] != signature:
                item['card'].hide(); item['card'].deleteLater()
                self.body_layout.removeWidget(item['card'])
                item = None
            if not item:
                card = QFrame(); card.setProperty('class', 'card')
                layout = QVBoxLayout(card)
                heading = QHBoxLayout()
                title = QLabel(); title.setWordWrap(True); title.setTextFormat(Qt.PlainText)
                title.setFont(QFont('Segoe UI', 14, QFont.Bold))
                heading.addWidget(title, 1)
                priority = PriorityControl()
                host.configure_priority_control(priority, name, self.provider)
                heading.addWidget(priority)
                layout.addLayout(heading)
                status, detail, uptime = QLabel(), QLabel(), QLabel()
                for label_widget in (status, detail, uptime):
                    label_widget.setWordWrap(True); label_widget.setTextFormat(Qt.PlainText); layout.addWidget(label_widget)
                uptime.setProperty('class', 'muted')
                tracks = {}
                for w in quota.get('windows', []):
                    label = QLabel(); layout.addWidget(label)
                    bar = ReserveBar(large=True); layout.addWidget(bar)
                    group, window = oauth_window_key(w['label'], self.provider)
                    host.bind_reserve_bar(bar, name, self.provider, group, window)
                    tracks[w['label']] = label, bar
                error = QLabel(); error.setWordWrap(True); error.setTextFormat(Qt.PlainText); layout.addWidget(error)
                controls = ActionGrid()
                buttons = []
                for key, callback in self.actions:
                    if key == 'chatgpt_reset' and not quota.get('reset_options'):
                        continue
                    button = QPushButton()
                    button.clicked.connect(lambda checked=False, n=name, action=callback: action(self.cards[n]['account']))
                    controls.addWidget(button); buttons.append((key, button))
                layout.addWidget(controls)
                item = {'card': card, 'structure': signature, 'title': title, 'priority': priority, 'status': status,
                        'detail': detail, 'uptime': uptime, 'tracks': tracks, 'error': error, 'buttons': buttons}
                self.cards[name] = item
            item['account'] = account
            self.body_layout.insertWidget(index, item['card'])
            item['title'].setText(host.display_name(account))
            item['priority'].set_value(account_priority(host.controller.preferences, name))
            state, severity, detail = account_status(account)
            reserve_text = None
            if quota.get('reserved_families') and severity != 'error' and not account.get('disabled'):
                state, severity = 'Quota reserve reached', 'warning'
                families = {'openai': 'ChatGPT', 'claude': 'Claude', 'claude-opus': 'Opus', 'claude-sonnet': 'Sonnet'}
                reserve_text = tr(state) + ' · ' + ' / '.join(families.get(f, f) for f in quota['reserved_families'])
            plan = quota.get('plan_type') or account.get('plan_type') or ''
            provider_title = {'codex': 'ChatGPT', 'claude': 'Claude'}.get(self.provider, self.provider.title())
            item['status'].setText(provider_title + (' · ' + str(plan) if plan else '') + ' · ' + (reserve_text or tr(state)))
            host.set_label_color(item['status'], 'warning' if severity in ('warning', 'error') else 'muted')
            detail_lines = [detail] if detail else []
            item['detail'].setText('\n'.join(detail_lines))
            item['detail'].setVisible(bool(detail_lines))
            uptime_text = host.uptime_text(self.provider, name)
            item['uptime'].setText(uptime_text or '')
            item['uptime'].setVisible(bool(uptime_text))
            for w in quota.get('windows', []):
                label, bar = item['tracks'][w['label']]
                try: until = host.time_until_reset(datetime.fromtimestamp(w['reset_at'], timezone.utc).isoformat())
                except (KeyError, ValueError, TypeError, OSError, OverflowError): until = '—'
                label.setText(f"{w['label']} · {w['remaining']:.1f}% · {until}")
                bar.set_value(w['remaining'] / 100); bar.set_color(host.quota_color(w['remaining'] / 100))
                bar.set_theme(host.theme.colors())
                group, window = oauth_window_key(w['label'], self.provider)
                bar.set_floor(quota_floor(host.controller.preferences, name, group, window))
            error = safe_detail(quota.get('error') or '')
            item['error'].setText(error); item['error'].setVisible(bool(error))
            for key, button in item['buttons']:
                button.setText(tr('api_resume' if account.get('disabled') else 'api_pause') if key == 'api_pause' else tr(key))
