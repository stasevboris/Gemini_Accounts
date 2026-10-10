"""Multilingual UI strings for Gemini Accounts.

Supported: English, Russian, Ukrainian, Belarusian, Simplified Chinese.
Usage:
    from locales import tr, set_language, current_language, LANGUAGES
    set_language('ru')
    label.setText(tr('app_title'))
    label.setText(tr('quota_accounts', count=3, total=5))
"""

LANGUAGES = {
    'en': 'English',
    'ru': 'Русский',
    'uk': 'Українська',
    'be': 'Беларуская',
    'zh': '中文',
}

_current = 'en'

# fmt: off
_strings = {

    # ── Window titles ─────────────────────────────────────────────────
    'app_title': {
        'en': 'Gemini Accounts',
        'ru': 'Gemini Аккаунты',
        'uk': 'Gemini Акаунти',
        'be': 'Gemini Акаўнты',
        'zh': 'Gemini 账户',
    },
    'win_model_selection': {
        'en': 'Model selection',
        'ru': 'Выбор модели',
        'uk': 'Вибір моделі',
        'be': 'Выбар мадэлі',
        'zh': '模型选择',
    },
    'win_connections': {
        'en': 'Application connections',
        'ru': 'Подключения приложений',
        'uk': 'З\'єднання додатків',
        'be': 'Злучэнні праграм',
        'zh': '应用连接',
    },
    'win_add_account': {
        'en': 'Add account',
        'ru': 'Добавить аккаунт',
        'uk': 'Додати акаунт',
        'be': 'Дадаць акаўнт',
        'zh': '添加账户',
    },

    # ── Sidebar header ────────────────────────────────────────────────
    'sidebar_title': {
        'en': '✦  Gemini Accounts',
        'ru': '✦  Gemini Аккаунты',
        'uk': '✦  Gemini Акаунти',
        'be': '✦  Gemini Акаўнты',
        'zh': '✦  Gemini 账户',
    },
    'btn_add_account': {
        'en': '+  Add Google account',
        'ru': '+  Добавить Google аккаунт',
        'uk': '+  Додати Google акаунт',
        'be': '+  Дадаць Google акаўнт',
        'zh': '+  添加 Google 账户',
    },
    'status_connecting': {
        'en': 'Connecting…',
        'ru': 'Подключение…',
        'uk': 'З\'єднання…',
        'be': 'Злучэнне…',
        'zh': '连接中…',
    },
    'status_connected': {
        'en': '●  Connected',
        'ru': '●  Подключено',
        'uk': '●  Підключено',
        'be': '●  Злучана',
        'zh': '●  已连接',
    },
    'status_attention': {
        'en': '●  Needs attention',
        'ru': '●  Требуется внимание',
        'uk': '●  Потребує уваги',
        'be': '●  Патрабуе ўвагі',
        'zh': '●  需要注意',
    },
    'quota_5h_pooled': {
        'en': 'Gemini · 5h · pooled remaining',
        'ru': 'Gemini · 5ч · общий остаток',
        'uk': 'Gemini · 5г · загальний залишок',
        'be': 'Gemini · 5г · агульны рэшта',
        'zh': 'Gemini · 5小时 · 汇总剩余',
    },
    'quota_1w_pooled': {
        'en': 'Gemini · 1w · pooled remaining',
        'ru': 'Gemini · 1н · общий остаток',
        'uk': 'Gemini · 1т · загальний залишок',
        'be': 'Gemini · 1т · агульны рэшта',
        'zh': 'Gemini · 1周 · 汇总剩余',
    },
    'quota_5h_data': {
        'en': 'Gemini · 5h · data {count}/{total} accounts',
        'ru': 'Gemini · 5ч · данные {count}/{total} аккаунтов',
        'uk': 'Gemini · 5г · дані {count}/{total} акаунтів',
        'be': 'Gemini · 5г · даныя {count}/{total} акаўнтаў',
        'zh': 'Gemini · 5小时 · 数据 {count}/{total} 个账户',
    },
    'quota_1w_data': {
        'en': 'Gemini · 1w · data {count}/{total} accounts',
        'ru': 'Gemini · 1н · данные {count}/{total} аккаунтов',
        'uk': 'Gemini · 1т · дані {count}/{total} акаунтів',
        'be': 'Gemini · 1т · даныя {count}/{total} акаўнтаў',
        'zh': 'Gemini · 1周 · 数据 {count}/{total} 个账户',
    },
    'group_verification_required': {
        'en': 'Verification required · {count}',
        'ru': 'Верификация · {count}',
        'uk': 'Верифікація · {count}',
        'be': 'Верыфікацыя · {count}',
        'zh': '需要验证 · {count}',
    },
    'group_ready_accounts': {
        'en': 'Ready accounts · {count}',
        'ru': 'Готовые аккаунты · {count}',
        'uk': 'Готові акаунти · {count}',
        'be': 'Гатовыя акаўнты · {count}',
        'zh': '就绪账户 · {count}',
    },

    # ── Body / Main area ──────────────────────────────────────────────
    'heading_saved_accounts': {
        'en': 'Saved accounts',
        'ru': 'Сохранённые аккаунты',
        'uk': 'Збережені акаунти',
        'be': 'Захаваныя акаўнты',
        'zh': '已保存的账户',
    },
    'subtitle_switch': {
        'en': 'Switch accounts while continuing your Claude sessions.',
        'ru': 'Переключайте аккаунты, не прерывая сессии Claude.',
        'uk': 'Перемикайте акаунти, не перериваючи сесії Claude.',
        'be': 'Пераключайце акаўнты, не перарываючы сесіі Claude.',
        'zh': '切换账户而不中断 Claude 会话。',
    },
    'loading_accounts': {
        'en': 'Loading accounts…',
        'ru': 'Загрузка аккаунтов…',
        'uk': 'Завантаження акаунтів…',
        'be': 'Загрузка акаўнтаў…',
        'zh': '加载账户中…',
    },
    'mode_connected_clients': {
        'en': 'Connected clients use the selected accounts.',
        'ru': 'Подключённые клиенты используют выбранные аккаунты.',
        'uk': 'Підключені клієнти використовують вибрані акаунти.',
        'be': 'Злучаныя кліенты выкарыстоўваюць абраныя акаўнты.',
        'zh': '已连接的客户端使用所选账户。',
    },
    'btn_use_all_auto': {
        'en': 'Use all • automatic routing',
        'ru': 'Использовать все • автомаршрутизация',
        'uk': 'Використовувати всі • автомаршрутизація',
        'be': 'Выкарыстоўваць усе • аўтамаршрутызацыя',
        'zh': '使用全部 • 自动路由',
    },
    'last_request_waiting': {
        'en': 'Last request: waiting for proxy data',
        'ru': 'Последний запрос: ожидание данных прокси',
        'uk': 'Останній запит: очікування даних проксі',
        'be': 'Апошні запыт: чаканне даных проксі',
        'zh': '上次请求：等待代理数据',
    },
    'btn_connect_apps': {
        'en': 'Connect applications',
        'ru': 'Подключить приложения',
        'uk': 'Підключити додатки',
        'be': 'Злучыць праграмы',
        'zh': '连接应用',
    },
    'tab_account_quotas': {
        'en': 'Account and quotas',
        'ru': 'Аккаунт и квоты',
        'uk': 'Акаунт і квоти',
        'be': 'Акаўнт і квоты',
        'zh': '账户与配额',
    },
    'tab_routing_stats': {
        'en': 'Routing statistics',
        'ru': 'Статистика маршрутизации',
        'uk': 'Статистика маршрутизації',
        'be': 'Статыстыка маршрутызацыі',
        'zh': '路由统计',
    },
    'notice_signins_preserved': {
        'en': 'Sign-ins are preserved when the application closes.',
        'ru': 'Авторизации сохраняются при закрытии приложения.',
        'uk': 'Авторизації зберігаються при закритті додатку.',
        'be': 'Аўтарызацыі захоўваюцца пры закрыцці праграмы.',
        'zh': '关闭应用时登录信息将被保留。',
    },

    # ── Mode labels ───────────────────────────────────────────────────
    'mode_no_accounts': {
        'en': 'No accounts enabled',
        'ru': 'Нет включённых аккаунтов',
        'uk': 'Немає ввімкнених акаунтів',
        'be': 'Няма ўключаных акаўнтаў',
        'zh': '没有启用的账户',
    },
    'mode_auto_routing': {
        'en': 'Automatic routing • enabled accounts: {count}',
        'ru': 'Автомаршрутизация • включено аккаунтов: {count}',
        'uk': 'Автомаршрутизація • увімкнено акаунтів: {count}',
        'be': 'Аўтамаршрутызацыя • ўключана акаўнтаў: {count}',
        'zh': '自动路由 • 已启用账户: {count}',
    },
    'mode_for_claude': {
        'en': 'For Claude: {name}',
        'ru': 'Для Claude: {name}',
        'uk': 'Для Claude: {name}',
        'be': 'Для Claude: {name}',
        'zh': 'Claude 使用: {name}',
    },
    'mode_enabled_of': {
        'en': 'Enabled accounts: {enabled} of {total}',
        'ru': 'Включено аккаунтов: {enabled} из {total}',
        'uk': 'Увімкнено акаунтів: {enabled} із {total}',
        'be': 'Уключана акаўнтаў: {enabled} з {total}',
        'zh': '已启用账户: {enabled} / {total}',
    },

    # ── Detail view ───────────────────────────────────────────────────
    'detail_add_first': {
        'en': 'Add your first account',
        'ru': 'Добавьте первый аккаунт',
        'uk': 'Додайте перший акаунт',
        'be': 'Дадайце першы акаўнт',
        'zh': '添加您的第一个账户',
    },
    'detail_add_hint': {
        'en': 'Click Add Google account and complete browser sign-in. Your saved account and available models will appear here.',
        'ru': 'Нажмите «Добавить Google аккаунт» и завершите вход в браузере. Сохранённый аккаунт и доступные модели появятся здесь.',
        'uk': 'Натисніть «Додати Google акаунт» та завершіть вхід у браузері. Збережений акаунт і доступні моделі з\'являться тут.',
        'be': 'Націсніце «Дадаць Google акаўнт» і завяршыце ўваход у браўзеры. Захаваны акаўнт і даступныя мадэлі з\'явяцца тут.',
        'zh': '点击"添加 Google 账户"并在浏览器中完成登录。保存的账户和可用模型将显示在此处。',
    },
    'detail_remaining_quota': {
        'en': 'Remaining quota',
        'ru': 'Остаток квоты',
        'uk': 'Залишок квоти',
        'be': 'Рэшта квоты',
        'zh': '剩余配额',
    },
    'detail_loading_quotas': {
        'en': 'Loading Google quotas…',
        'ru': 'Загрузка квот Google…',
        'uk': 'Завантаження квот Google…',
        'be': 'Загрузка квот Google…',
        'zh': '加载 Google 配额…',
    },
    'detail_5h_quota': {
        'en': '5-hour quota',
        'ru': '5-часовая квота',
        'uk': '5-годинна квота',
        'be': '5-гадзінная квота',
        'zh': '5小时配额',
    },
    'detail_weekly_quota': {
        'en': 'Weekly quota',
        'ru': 'Недельная квота',
        'uk': 'Тижнева квота',
        'be': 'Тыднёвая квота',
        'zh': '每周配额',
    },
    'detail_bars_hint': {
        'en': 'Bars show remaining quota: full = 100%. Missing percentages are shown as No data.',
        'ru': 'Полоски показывают остаток квоты: полная = 100%. Отсутствующие данные отображаются как «Нет данных».',
        'uk': 'Смужки показують залишок квоти: повна = 100%. Відсутні дані відображаються як «Немає даних».',
        'be': 'Палоскі паказваюць рэшту квоты: поўная = 100%. Адсутныя даныя паказваюцца як «Няма даных».',
        'zh': '进度条显示剩余配额：满格 = 100%。缺失的百分比显示为"无数据"。',
    },
    'btn_use_only_this': {
        'en': 'Use only this account',
        'ru': 'Использовать только этот',
        'uk': 'Використовувати тільки цей',
        'be': 'Выкарыстоўваць толькі гэты',
        'zh': '仅使用此账户',
    },
    'btn_pause': {
        'en': 'Pause',
        'ru': 'Приостановить',
        'uk': 'Призупинити',
        'be': 'Прыпыніць',
        'zh': '暂停',
    },
    'btn_resume': {
        'en': 'Resume',
        'ru': 'Возобновить',
        'uk': 'Відновити',
        'be': 'Аднавіць',
        'zh': '恢复',
    },
    'btn_remove_account': {
        'en': 'Remove account',
        'ru': 'Удалить аккаунт',
        'uk': 'Видалити акаунт',
        'be': 'Выдаліць акаўнт',
        'zh': '移除账户',
    },
    'placeholder_label': {
        'en': 'Account label, e.g. Personal',
        'ru': 'Метка аккаунта, напр. Личный',
        'uk': 'Мітка акаунта, напр. Особистий',
        'be': 'Метка акаўнта, напр. Асабісты',
        'zh': '账户标签，例如"个人"',
    },
    'btn_save_label': {
        'en': 'Save label',
        'ru': 'Сохранить метку',
        'uk': 'Зберегти мітку',
        'be': 'Захаваць метку',
        'zh': '保存标签',
    },
    'detail_paused': {
        'en': 'Sign-in saved • account paused',
        'ru': 'Вход сохранён • аккаунт приостановлен',
        'uk': 'Вхід збережено • акаунт призупинено',
        'be': 'Уваход захаваны • акаўнт прыпынены',
        'zh': '登录已保存 • 账户已暂停',
    },
    'detail_enabled': {
        'en': 'Sign-in saved • enabled for requests',
        'ru': 'Вход сохранён • активен для запросов',
        'uk': 'Вхід збережено • активний для запитів',
        'be': 'Уваход захаваны • актыўны для запытаў',
        'zh': '登录已保存 • 已启用请求',
    },
    'detail_pause_hint': {
        'en': 'Pausing preserves the sign-in. Switching applies to future requests; an ongoing response may finish on the previous account.',
        'ru': 'Приостановка сохраняет авторизацию. Переключение применяется к будущим запросам; текущий ответ может завершиться на предыдущем аккаунте.',
        'uk': 'Призупинення зберігає авторизацію. Перемикання стосується майбутніх запитів; поточна відповідь може завершитися на попередньому акаунті.',
        'be': 'Прыпынак захоўвае аўтарызацыю. Пераключэнне датычыцца будучых запытаў; бягучы адказ можа завяршыцца на папярэднім акаўнце.',
        'zh': '暂停会保留登录信息。切换仅影响未来请求；正在进行的响应可能在前一个账户上完成。',
    },
    'detail_unavailable': {
        'en': 'The service reported temporary unavailability. Your sign-in is saved; you can select another account.',
        'ru': 'Сервис сообщил о временной недоступности. Ваш вход сохранён; вы можете выбрать другой аккаунт.',
        'uk': 'Сервіс повідомив про тимчасову недоступність. Ваш вхід збережено; ви можете вибрати інший акаунт.',
        'be': 'Сэрвіс паведаміў аб часовай недаступнасці. Ваш уваход захаваны; вы можаце абраць іншы акаўнт.',
        'zh': '服务报告暂时不可用。您的登录已保存；您可以选择其他账户。',
    },

    # ── Quota display ─────────────────────────────────────────────────
    'quota_no_data': {
        'en': 'No data',
        'ru': 'Нет данных',
        'uk': 'Немає даних',
        'be': 'Няма даных',
        'zh': '无数据',
    },
    'quota_remaining': {
        'en': '{percent} remaining',
        'ru': '{percent} осталось',
        'uk': '{percent} залишилось',
        'be': '{percent} засталося',
        'zh': '剩余 {percent}',
    },
    'quota_reset_at': {
        'en': 'Resets: {date} (local time)',
        'ru': 'Обновление: {date} (местное время)',
        'uk': 'Оновлення: {date} (місцевий час)',
        'be': 'Абнаўленне: {date} (мясцовы час)',
        'zh': '重置: {date}（本地时间）',
    },
    'quota_reset_unknown': {
        'en': 'Reset time not provided',
        'ru': 'Время обновления не указано',
        'uk': 'Час оновлення не вказано',
        'be': 'Час абнаўлення не ўказаны',
        'zh': '未提供重置时间',
    },
    'quota_updated_at': {
        'en': 'Updated {time} • automatically every minute',
        'ru': 'Обновлено {time} • автоматически каждую минуту',
        'uk': 'Оновлено {time} • автоматично кожну хвилину',
        'be': 'Абноўлена {time} • аўтаматычна кожную хвіліну',
        'zh': '更新于 {time} • 每分钟自动更新',
    },
    'quota_not_received': {
        'en': 'Quota data not received yet • automatically every minute',
        'ru': 'Данные квот ещё не получены • автоматически каждую минуту',
        'uk': 'Дані квот ще не отримано • автоматично кожну хвилину',
        'be': 'Даныя квот яшчэ не атрыманы • аўтаматычна кожную хвіліну',
        'zh': '配额数据尚未接收 • 每分钟自动更新',
    },

    # ── Account status ────────────────────────────────────────────────
    'account_paused': {
        'en': 'Paused',
        'ru': 'Приостановлен',
        'uk': 'Призупинено',
        'be': 'Прыпынены',
        'zh': '已暂停',
    },
    'account_waiting': {
        'en': 'Waiting / quota',
        'ru': 'Ожидание / квота',
        'uk': 'Очікування / квота',
        'be': 'Чаканне / квота',
        'zh': '等待中 / 配额',
    },
    'account_available': {
        'en': 'Available',
        'ru': 'Доступен',
        'uk': 'Доступний',
        'be': 'Даступны',
        'zh': '可用',
    },
    'account_last_response': {
        'en': 'Last response {time}',
        'ru': 'Последний ответ {time}',
        'uk': 'Остання відповідь {time}',
        'be': 'Апошні адказ {time}',
        'zh': '上次响应 {time}',
    },
    'account_verification_required': {
        'en': 'Google verification required',
        'ru': 'Требуется верификация Google',
        'uk': 'Потрібна верифікація Google',
        'be': 'Патрабуецца верыфікацыя Google',
        'zh': '需要 Google 验证',
    },
    'account_sign_in_again': {
        'en': 'Sign in again',
        'ru': 'Войдите снова',
        'uk': 'Увійдіть знову',
        'be': 'Увайдзіце зноў',
        'zh': '请重新登录',
    },
    'account_denied': {
        'en': 'Google denied access',
        'ru': 'Google отказал в доступе',
        'uk': 'Google відмовив у доступі',
        'be': 'Google адмовіў у доступе',
        'zh': 'Google 拒绝访问',
    },
    'account_responses': {
        'en': '{count} responses',
        'ru': '{count} ответов',
        'uk': '{count} відповідей',
        'be': '{count} адказаў',
        'zh': '{count} 次响应',
    },

    # ── Routing / Stats view ──────────────────────────────────────────
    'stats_auto_routing': {
        'en': 'Automatic routing',
        'ru': 'Автоматическая маршрутизация',
        'uk': 'Автоматична маршрутизація',
        'be': 'Аўтаматычная маршрутызацыя',
        'zh': '自动路由',
    },
    'btn_save_diag': {
        'en': 'Save diagnostic log…',
        'ru': 'Сохранить диагностику…',
        'uk': 'Зберегти діагностику…',
        'be': 'Захаваць дыягностыку…',
        'zh': '保存诊断日志…',
    },
    'btn_send_diag': {
        'en': 'Send diagnostic log…',
        'ru': 'Отправить диагностику…',
        'uk': 'Надіслати діагностику…',
        'be': 'Адправіць дыягностыку…',
        'zh': '发送诊断日志…',
    },
    'btn_check_updates': {
        'en': 'Check for updates',
        'ru': 'Проверить обновления',
        'uk': 'Перевірити оновлення',
        'be': 'Праверыць абнаўленні',
        'zh': '检查更新',
    },
    'stats_starting': {
        'en': 'Starting monitoring…',
        'ru': 'Запуск мониторинга…',
        'uk': 'Запуск моніторингу…',
        'be': 'Запуск маніторынгу…',
        'zh': '启动监控…',
    },
    'stats_priority_heading': {
        'en': 'Priority: earliest reset among available accounts',
        'ru': 'Приоритет: ближайшее обновление среди доступных аккаунтов',
        'uk': 'Пріоритет: найраніше оновлення серед доступних акаунтів',
        'be': 'Прыярытэт: найбліжэйшае абнаўленне сярод даступных акаўнтаў',
        'zh': '优先级：可用账户中最早重置的账户',
    },
    'stats_current_model': {
        'en': 'Current model',
        'ru': 'Текущая модель',
        'uk': 'Поточна модель',
        'be': 'Бягучая мадэль',
        'zh': '当前模型',
    },
    'stats_loading_quotas': {
        'en': 'Loading quotas to rank accounts…',
        'ru': 'Загрузка квот для ранжирования аккаунтов…',
        'uk': 'Завантаження квот для ранжування акаунтів…',
        'be': 'Загрузка квот для ранжыравання акаўнтаў…',
        'zh': '加载配额以排序账户…',
    },
    'stats_last_success_none': {
        'en': 'Last successful request: no data yet',
        'ru': 'Последний успешный запрос: данных пока нет',
        'uk': 'Останній успішний запит: даних поки немає',
        'be': 'Апошні паспяховы запыт: даных пакуль няма',
        'zh': '上次成功请求：暂无数据',
    },
    'stats_last_success': {
        'en': 'Last successful request: {name}',
        'ru': 'Последний успешный запрос: {name}',
        'uk': 'Останній успішний запит: {name}',
        'be': 'Апошні паспяховы запыт: {name}',
        'zh': '上次成功请求: {name}',
    },
    'stats_last_response': {
        'en': 'Last response: {name} • {time}',
        'ru': 'Последний ответ: {name} • {time}',
        'uk': 'Остання відповідь: {name} • {time}',
        'be': 'Апошні адказ: {name} • {time}',
        'zh': '上次响应: {name} • {time}',
    },
    'stats_accounts_note': {
        'en': 'Accounts are identified from completed requests. The proxy does not report the account during generation. Different models may use different accounts.',
        'ru': 'Аккаунты определяются по завершённым запросам. Прокси не сообщает аккаунт во время генерации. Разные модели могут использовать разные аккаунты.',
        'uk': 'Акаунти визначаються за завершеними запитами. Проксі не повідомляє акаунт під час генерації. Різні моделі можуть використовувати різні акаунти.',
        'be': 'Акаўнты вызначаюцца па завершаных запытах. Проксі не паведамляе акаўнт падчас генерацыі. Розныя мадэлі могуць выкарыстоўваць розныя акаўнты.',
        'zh': '账户根据已完成的请求识别。代理在生成过程中不报告账户。不同模型可能使用不同账户。',
    },
    'stats_filter_all': {
        'en': 'All events',
        'ru': 'Все события',
        'uk': 'Всі події',
        'be': 'Усе падзеі',
        'zh': '所有事件',
    },
    'stats_filter_switches': {
        'en': 'Switches',
        'ru': 'Переключения',
        'uk': 'Перемикання',
        'be': 'Пераключэнні',
        'zh': '切换',
    },
    'stats_filter_errors': {
        'en': 'Errors',
        'ru': 'Ошибки',
        'uk': 'Помилки',
        'be': 'Памылкі',
        'zh': '错误',
    },
    'stats_journal_heading': {
        'en': 'Requests and account switches',
        'ru': 'Запросы и переключения аккаунтов',
        'uk': 'Запити та перемикання акаунтів',
        'be': 'Запыты і пераключэнні акаўнтаў',
        'zh': '请求和账户切换',
    },
    'stats_no_events': {
        'en': 'No events yet. New requests will appear automatically.',
        'ru': 'Событий пока нет. Новые запросы появятся автоматически.',
        'uk': 'Подій поки немає. Нові запити з\'являться автоматично.',
        'be': 'Падзей пакуль няма. Новыя запыты з\'явяцца аўтаматычна.',
        'zh': '暂无事件。新请求将自动出现。',
    },
    'stats_totals': {
        'en': 'Since monitoring started: {success} responses • {failed} errors • {switches} switches in the log • {tokens} tokens',
        'ru': 'С начала мониторинга: {success} ответов • {failed} ошибок • {switches} переключений в журнале • {tokens} токенов',
        'uk': 'З початку моніторингу: {success} відповідей • {failed} помилок • {switches} перемикань у журналі • {tokens} токенів',
        'be': 'З пачатку маніторынгу: {success} адказаў • {failed} памылак • {switches} пераключэнняў у журнале • {tokens} токенаў',
        'zh': '自监控开始: {success} 次响应 • {failed} 次错误 • {switches} 次切换 • {tokens} 个令牌',
    },
    'stats_monitoring_since': {
        'en': 'Monitoring since {time} (local time). The log persists after closing; monitoring runs while the application is open. The latest 2000 events are kept.',
        'ru': 'Мониторинг с {time} (местное время). Журнал сохраняется после закрытия; мониторинг работает, пока приложение открыто. Хранятся последние 2000 событий.',
        'uk': 'Моніторинг з {time} (місцевий час). Журнал зберігається після закриття; моніторинг працює, поки додаток відкритий. Зберігаються останні 2000 подій.',
        'be': 'Маніторынг з {time} (мясцовы час). Журнал захоўваецца пасля закрыцця; маніторынг працуе, пакуль праграма адкрыта. Захоўваюцца апошнія 2000 падзей.',
        'zh': '自 {time} 开始监控（本地时间）。日志在关闭后保留；监控在应用打开期间运行。保留最近 2000 条事件。',
    },
    'stats_strategy_earliest': {
        'en': 'Earliest-reset priority',
        'ru': 'Приоритет ближайшего обновления',
        'uk': 'Пріоритет найранішого оновлення',
        'be': 'Прыярытэт найбліжэйшага абнаўлення',
        'zh': '最早重置优先',
    },
    'stats_strategy_fill': {
        'en': 'Fill one account first → switch when unavailable',
        'ru': 'Сначала один аккаунт → переключение при недоступности',
        'uk': 'Спочатку один акаунт → перемикання при недоступності',
        'be': 'Спачатку адзін акаўнт → пераключэнне пры недаступнасці',
        'zh': '先用一个账户 → 不可用时切换',
    },
    'stats_strategy_roundrobin': {
        'en': 'Round-robin accounts',
        'ru': 'Ротация аккаунтов',
        'uk': 'Ротація акаунтів',
        'be': 'Ратацыя акаўнтаў',
        'zh': '轮询账户',
    },
    'stats_enabled_accounts': {
        'en': 'enabled accounts: {count} • updated every 5 seconds',
        'ru': 'включено аккаунтов: {count} • обновляется каждые 5 секунд',
        'uk': 'увімкнено акаунтів: {count} • оновлюється кожні 5 секунд',
        'be': 'уключана акаўнтаў: {count} • абнаўляецца кожныя 5 секунд',
        'zh': '已启用账户: {count} • 每5秒更新',
    },
    'policy_manual': {
        'en': 'One account is selected manually. Automatic ranking is paused.',
        'ru': 'Один аккаунт выбран вручную. Автоматическое ранжирование приостановлено.',
        'uk': 'Один акаунт вибрано вручну. Автоматичне ранжування призупинено.',
        'be': 'Адзін акаўнт абраны ўручную. Аўтаматычнае ранжыраванне прыпынена.',
        'zh': '已手动选择一个账户。自动排序已暂停。',
    },
    'policy_ranking': {
        'en': 'Account ranking for {title} • recalculated after quota updates.',
        'ru': 'Ранжирование аккаунтов {title} • пересчитывается после обновления квот.',
        'uk': 'Ранжування акаунтів {title} • перераховується після оновлення квот.',
        'be': 'Ранжыраванне акаўнтаў {title} • пералічваецца пасля абнаўлення квот.',
        'zh': '{title} 账户排名 • 配额更新后重新计算。',
    },
    'policy_footer': {
        'en': 'Proxy priorities are calculated for this group. The last ranking remains active after the application closes.',
        'ru': 'Приоритеты прокси рассчитаны для этой группы. Последнее ранжирование остаётся активным после закрытия приложения.',
        'uk': 'Пріоритети проксі розраховані для цієї групи. Останнє ранжування залишається активним після закриття додатку.',
        'be': 'Прыярытэты проксі разлічаны для гэтай групы. Апошняе ранжыраванне застаецца актыўным пасля закрыцця праграмы.',
        'zh': '代理优先级已为此组计算。最后的排名在应用关闭后仍然有效。',
    },
    'policy_mode_note': {
        'en': 'Earliest-reset priority • {title}. Quotas and errors are handled automatically.',
        'ru': 'Приоритет ближайшего обновления • {title}. Квоты и ошибки обрабатываются автоматически.',
        'uk': 'Пріоритет найранішого оновлення • {title}. Квоти та помилки обробляються автоматично.',
        'be': 'Прыярытэт найбліжэйшага абнаўлення • {title}. Квоты і памылкі апрацоўваюцца аўтаматычна.',
        'zh': '最早重置优先 • {title}。配额和错误自动处理。',
    },

    # ── Updates ────────────────────────────────────────────────────────
    'update_checking': {
        'en': 'Checking updates…',
        'ru': 'Проверка обновлений…',
        'uk': 'Перевірка оновлень…',
        'be': 'Праверка абнаўленняў…',
        'zh': '检查更新中…',
    },
    'update_up_to_date': {
        'en': 'Up to date · check again',
        'ru': 'Актуальная версия · проверить снова',
        'uk': 'Актуальна · перевірити знову',
        'be': 'Актуальная версія · праверыць зноў',
        'zh': '已是最新版 · 再次检查',
    },
    'update_to_version': {
        'en': 'Update to {version}',
        'ru': 'Обновить до {version}',
        'uk': 'Оновити до {version}',
        'be': 'Абнавіць да {version}',
        'zh': '更新到 {version}',
    },
    'update_downloading': {
        'en': 'Downloading update…',
        'ru': 'Загрузка обновления…',
        'uk': 'Завантаження оновлення…',
        'be': 'Загрузка абнаўлення…',
        'zh': '下载更新中…',
    },
    'update_waiting': {
        'en': 'Update ready · waiting for requests…',
        'ru': 'Обновление готово · ожидание завершения запросов…',
        'uk': 'Оновлення готове · очікування завершення запитів…',
        'be': 'Абнаўленне гатова · чаканне завяршэння запытаў…',
        'zh': '更新就绪 · 等待请求完成…',
    },
    'update_installing': {
        'en': 'Installing and restarting…',
        'ru': 'Установка и перезапуск…',
        'uk': 'Встановлення та перезапуск…',
        'be': 'Усталяванне і перазапуск…',
        'zh': '安装并重启中…',
    },
    'update_retry': {
        'en': 'Retry update',
        'ru': 'Повторить обновление',
        'uk': 'Повторити оновлення',
        'be': 'Паўтарыць абнаўленне',
        'zh': '重试更新',
    },

    # ── Model settings dialog ─────────────────────────────────────────
    'models_heading': {
        'en': 'Choose models',
        'ru': 'Выбор моделей',
        'uk': 'Вибір моделей',
        'be': 'Выбар мадэлей',
        'zh': '选择模型',
    },
    'models_hint': {
        'en': 'Choose Claude and Gemini models independently.\nNew requests use your choice. Ongoing responses keep their model.',
        'ru': 'Выбирайте модели Claude и Gemini независимо.\nНовые запросы используют ваш выбор. Текущие ответы сохраняют свою модель.',
        'uk': 'Обирайте моделі Claude та Gemini незалежно.\nНові запити використовують ваш вибір. Поточні відповіді зберігають свою модель.',
        'be': 'Выбірайце мадэлі Claude і Gemini незалежна.\nНовыя запыты выкарыстоўваюць ваш выбар. Бягучыя адказы захоўваюць сваю мадэль.',
        'zh': '独立选择 Claude 和 Gemini 模型。\n新请求使用您的选择。正在进行的响应保持其模型。',
    },
    'models_claude_group': {
        'en': 'Claude (Antigravity)',
        'ru': 'Claude (Antigravity)',
        'uk': 'Claude (Antigravity)',
        'be': 'Claude (Antigravity)',
        'zh': 'Claude (Antigravity)',
    },
    'models_gemini_group': {
        'en': 'Gemini',
        'ru': 'Gemini',
        'uk': 'Gemini',
        'be': 'Gemini',
        'zh': 'Gemini',
    },
    'models_loading': {
        'en': 'Loading…',
        'ru': 'Загрузка…',
        'uk': 'Завантаження…',
        'be': 'Загрузка…',
        'zh': '加载中…',
    },
    'models_update_clients': {
        'en': 'Update connected client model menus (asks permission)',
        'ru': 'Обновить меню моделей подключённых клиентов (запросит разрешение)',
        'uk': 'Оновити меню моделей підключених клієнтів (запитає дозвіл)',
        'be': 'Абнавіць меню мадэлей злучаных кліентаў (запытае дазвол)',
        'zh': '更新已连接客户端的模型菜单（需要许可）',
    },
    'models_loading_catalog': {
        'en': 'Loading the account model catalog…',
        'ru': 'Загрузка каталога моделей…',
        'uk': 'Завантаження каталогу моделей…',
        'be': 'Загрузка каталога мадэлей…',
        'zh': '加载账户模型目录…',
    },
    'btn_apply_models': {
        'en': 'Apply models',
        'ru': 'Применить модели',
        'uk': 'Застосувати моделі',
        'be': 'Ужыць мадэлі',
        'zh': '应用模型',
    },
    'models_applied': {
        'en': 'Applied to new gateway requests.',
        'ru': 'Применено к новым запросам шлюза.',
        'uk': 'Застосовано до нових запитів шлюзу.',
        'be': 'Ужыта да новых запытаў шлюзу.',
        'zh': '已应用于新的网关请求。',
    },
    'models_applied_restart': {
        'en': 'Applied to new gateway requests. Restart clients for updated menus and defaults.',
        'ru': 'Применено к новым запросам шлюза. Перезапустите клиенты для обновления меню.',
        'uk': 'Застосовано до нових запитів шлюзу. Перезапустіть клієнти для оновлення меню.',
        'be': 'Ужыта да новых запытаў шлюзу. Перазапусціце кліенты для абнаўлення меню.',
        'zh': '已应用于新的网关请求。重启客户端以更新菜单和默认设置。',
    },
    'models_quota_note': {
        'en': 'Claude uses the Antigravity Claude quota. Gemini uses the Gemini quota.',
        'ru': 'Claude использует квоту Antigravity Claude. Gemini использует квоту Gemini.',
        'uk': 'Claude використовує квоту Antigravity Claude. Gemini використовує квоту Gemini.',
        'be': 'Claude выкарыстоўвае квоту Antigravity Claude. Gemini выкарыстоўвае квоту Gemini.',
        'zh': 'Claude 使用 Antigravity Claude 配额。Gemini 使用 Gemini 配额。',
    },

    # ── Connection settings dialog ────────────────────────────────────
    'conn_heading': {
        'en': 'Set up connections',
        'ru': 'Настройка подключений',
        'uk': 'Налаштування підключень',
        'be': 'Наладка злучэнняў',
        'zh': '设置连接',
    },
    'conn_hint': {
        'en': 'Choose applications. We will configure the local connection\nand back up your original configurations for restoration.',
        'ru': 'Выберите приложения. Мы настроим локальное подключение\nи сохраним резервные копии оригинальных конфигураций.',
        'uk': 'Виберіть додатки. Ми налаштуємо локальне підключення\nта збережемо резервні копії оригінальних конфігурацій.',
        'be': 'Выберыце праграмы. Мы наладзім лакальнае злучэнне\nі захаваем рэзервовыя копіі арыгінальных канфігурацый.',
        'zh': '选择应用。我们将配置本地连接\n并备份您的原始配置以便恢复。',
    },
    'conn_claude_desktop': {
        'en': 'Claude Desktop · Code tab',
        'ru': 'Claude Desktop · вкладка Code',
        'uk': 'Claude Desktop · вкладка Code',
        'be': 'Claude Desktop · укладка Code',
        'zh': 'Claude Desktop · Code 选项卡',
    },
    'conn_codex': {
        'en': 'Codex Desktop and CLI',
        'ru': 'Codex Desktop и CLI',
        'uk': 'Codex Desktop та CLI',
        'be': 'Codex Desktop і CLI',
        'zh': 'Codex Desktop 和 CLI',
    },
    'conn_claude_cli': {
        'en': 'Claude Code CLI',
        'ru': 'Claude Code CLI',
        'uk': 'Claude Code CLI',
        'be': 'Claude Code CLI',
        'zh': 'Claude Code CLI',
    },
    'conn_not_detected': {
        'en': ' · not detected',
        'ru': ' · не обнаружен',
        'uk': ' · не знайдено',
        'be': ' · не знойдзена',
        'zh': ' · 未检测到',
    },
    'conn_sessions_preserved': {
        'en': 'Client sessions, projects and sign-ins are preserved.',
        'ru': 'Сессии, проекты и авторизации клиентов сохраняются.',
        'uk': 'Сесії, проекти та авторизації клієнтів зберігаються.',
        'be': 'Сесіі, праекты і аўтарызацыі кліентаў захоўваюцца.',
        'zh': '客户端会话、项目和登录信息将被保留。',
    },
    'btn_configure_apps': {
        'en': 'Configure selected applications',
        'ru': 'Настроить выбранные приложения',
        'uk': 'Налаштувати вибрані додатки',
        'be': 'Наладзіць абраныя праграмы',
        'zh': '配置所选应用',
    },
    'btn_restore_settings': {
        'en': 'Restore previous settings / reset preferences',
        'ru': 'Восстановить прежние настройки / сброс',
        'uk': 'Відновити попередні налаштування / скинути',
        'be': 'Аднавіць папярэднія налады / скід',
        'zh': '恢复以前的设置 / 重置首选项',
    },
    'conn_configured': {
        'en': 'Connections configured. Launch CLI clients as usual.',
        'ru': 'Подключения настроены. Запускайте CLI-клиенты как обычно.',
        'uk': 'Підключення налаштовано. Запускайте CLI-клієнти як зазвичай.',
        'be': 'Злучэнні наладжаны. Запускайце CLI-кліенты як звычайна.',
        'zh': '连接已配置。像往常一样启动 CLI 客户端。',
    },
    'conn_restarted': {
        'en': 'Applications restarted with the new connection.',
        'ru': 'Приложения перезапущены с новым подключением.',
        'uk': 'Додатки перезапущено з новим підключенням.',
        'be': 'Праграмы перазапушчаны з новым злучэннем.',
        'zh': '应用已使用新连接重启。',
    },
    'conn_restored': {
        'en': 'Original configurations restored: {count}. Restart running clients.',
        'ru': 'Оригинальные конфигурации восстановлены: {count}. Перезапустите клиенты.',
        'uk': 'Оригінальні конфігурації відновлено: {count}. Перезапустіть клієнти.',
        'be': 'Арыгінальныя канфігурацыі адноўлены: {count}. Перазапусціце кліенты.',
        'zh': '已恢复原始配置: {count} 个。重启运行中的客户端。',
    },
    'conn_restored_restarted': {
        'en': 'Applications restarted with original settings.',
        'ru': 'Приложения перезапущены с оригинальными настройками.',
        'uk': 'Додатки перезапущено з оригінальними налаштуваннями.',
        'be': 'Праграмы перазапушчаны з арыгінальнымі наладамі.',
        'zh': '应用已使用原始设置重启。',
    },
    'conn_choose_one': {
        'en': 'Choose at least one application.',
        'ru': 'Выберите хотя бы одно приложение.',
        'uk': 'Виберіть хоча б один додаток.',
        'be': 'Выберыце хаця б адну праграму.',
        'zh': '请至少选择一个应用。',
    },

    # ── Login flow ────────────────────────────────────────────────────
    'login_heading': {
        'en': 'Complete Google sign-in',
        'ru': 'Завершите вход в Google',
        'uk': 'Завершіть вхід у Google',
        'be': 'Завяршыце ўваход у Google',
        'zh': '完成 Google 登录',
    },
    'login_hint': {
        'en': 'Choose an account in the opened browser.\nThe saved sign-in will appear in the list automatically.',
        'ru': 'Выберите аккаунт в открытом браузере.\nСохранённый вход появится в списке автоматически.',
        'uk': 'Виберіть акаунт у відкритому браузері.\nЗбережений вхід з\'явиться у списку автоматично.',
        'be': 'Выберыце акаўнт у адкрытым браўзеры.\nЗахаваны ўваход з\'явіцца ў спісе аўтаматычна.',
        'zh': '在打开的浏览器中选择账户。\n保存的登录将自动出现在列表中。',
    },
    'btn_reopen_signin': {
        'en': 'Reopen sign-in page',
        'ru': 'Открыть страницу входа заново',
        'uk': 'Відкрити сторінку входу заново',
        'be': 'Адкрыць старонку ўваходу нанова',
        'zh': '重新打开登录页面',
    },
    'login_waiting': {
        'en': 'Waiting for sign-in… You can close this window.',
        'ru': 'Ожидание входа… Вы можете закрыть это окно.',
        'uk': 'Очікування входу… Ви можете закрити це вікно.',
        'be': 'Чаканне ўваходу… Вы можаце закрыць гэта акно.',
        'zh': '等待登录中… 您可以关闭此窗口。',
    },
    'login_browser_hint': {
        'en': 'Choose your Google account in the browser and complete sign-in. It will appear here automatically.',
        'ru': 'Выберите аккаунт Google в браузере и завершите вход. Он появится здесь автоматически.',
        'uk': 'Виберіть акаунт Google у браузері та завершіть вхід. Він з\'явиться тут автоматично.',
        'be': 'Выберыце акаўнт Google у браўзеры і завяршыце ўваход. Ён з\'явіцца тут аўтаматычна.',
        'zh': '在浏览器中选择您的 Google 账户并完成登录。它将自动出现在此处。',
    },
    'login_timeout': {
        'en': 'Sign-in timed out. Click Add Google account again.',
        'ru': 'Время входа истекло. Нажмите «Добавить Google аккаунт» снова.',
        'uk': 'Час входу минув. Натисніть «Додати Google акаунт» знову.',
        'be': 'Час уваходу скончыўся. Націсніце «Дадаць Google акаўнт» зноў.',
        'zh': '登录超时。请再次点击"添加 Google 账户"。',
    },
    'login_saved': {
        'en': 'Account saved. You can select it for Claude.',
        'ru': 'Аккаунт сохранён. Вы можете выбрать его для Claude.',
        'uk': 'Акаунт збережено. Ви можете вибрати його для Claude.',
        'be': 'Акаўнт захаваны. Вы можаце абраць яго для Claude.',
        'zh': '账户已保存。您可以选择它用于 Claude。',
    },
    'login_failed': {
        'en': 'Google sign-in did not finish. Try adding the account again.',
        'ru': 'Вход в Google не завершён. Попробуйте добавить аккаунт снова.',
        'uk': 'Вхід у Google не завершено. Спробуйте додати акаунт знову.',
        'be': 'Уваход у Google не завершаны. Паспрабуйце дадаць акаўнт зноў.',
        'zh': 'Google 登录未完成。请再次尝试添加账户。',
    },
    'login_verified_auto': {
        'en': 'Account verified and added to automatic routing.',
        'ru': 'Аккаунт верифицирован и добавлен в автомаршрутизацию.',
        'uk': 'Акаунт верифіковано та додано до автомаршрутизації.',
        'be': 'Акаўнт верыфікаваны і дададзены ў аўтамаршрутызацыю.',
        'zh': '账户已验证并添加到自动路由。',
    },
    'login_verified_manual': {
        'en': 'Account verified. Another account is currently selected manually.',
        'ru': 'Аккаунт верифицирован. Другой аккаунт выбран вручную.',
        'uk': 'Акаунт верифіковано. Інший акаунт зараз вибрано вручну.',
        'be': 'Акаўнт верыфікаваны. Іншы акаўнт абраны ўручную.',
        'zh': '账户已验证。当前已手动选择其他账户。',
    },
    'login_needs_verification': {
        'en': 'Google requires verification of this account. Opening the page; controls are at the top of the list.',
        'ru': 'Google требует верификацию этого аккаунта. Открываем страницу; кнопки управления вверху списка.',
        'uk': 'Google вимагає верифікацію цього акаунта. Відкриваємо сторінку; кнопки управління зверху списку.',
        'be': 'Google патрабуе верыфікацыю гэтага акаўнта. Адкрываем старонку; кнопкі кіравання ўверсе спіса.',
        'zh': 'Google 需要验证此账户。正在打开页面；控制按钮在列表顶部。',
    },

    # ── Action results ────────────────────────────────────────────────
    'action_routing_enabled': {
        'en': 'Automatic routing enabled.',
        'ru': 'Автомаршрутизация включена.',
        'uk': 'Автомаршрутизацію увімкнено.',
        'be': 'Аўтамаршрутызацыя ўключана.',
        'zh': '自动路由已启用。',
    },
    'action_account_selected': {
        'en': 'Account selected for Claude.',
        'ru': 'Аккаунт выбран для Claude.',
        'uk': 'Акаунт вибрано для Claude.',
        'be': 'Акаўнт абраны для Claude.',
        'zh': '已选择账户用于 Claude。',
    },
    'action_status_updated': {
        'en': 'Account status updated.',
        'ru': 'Статус аккаунта обновлён.',
        'uk': 'Статус акаунта оновлено.',
        'be': 'Статус акаўнта абноўлены.',
        'zh': '账户状态已更新。',
    },
    'action_removed': {
        'en': 'Account removed. You can add it again by signing in.',
        'ru': 'Аккаунт удалён. Вы можете добавить его снова, войдя в систему.',
        'uk': 'Акаунт видалено. Ви можете додати його знову, увійшовши в систему.',
        'be': 'Акаўнт выдалены. Вы можаце дадаць яго зноў, увайшоўшы ў сістэму.',
        'zh': '账户已移除。您可以重新登录来再次添加。',
    },
    'action_label_error': {
        'en': 'Could not save the account label.',
        'ru': 'Не удалось сохранить метку аккаунта.',
        'uk': 'Не вдалося зберегти мітку акаунта.',
        'be': 'Не атрымалася захаваць метку акаўнта.',
        'zh': '无法保存账户标签。',
    },
    'action_verification_copied': {
        'en': 'Verification link copied.',
        'ru': 'Ссылка для верификации скопирована.',
        'uk': 'Посилання для верифікації скопійовано.',
        'be': 'Спасылка для верыфікацыі скапіявана.',
        'zh': '验证链接已复制。',
    },
    'action_verification_refresh_first': {
        'en': 'Refresh the link using ↻ first.',
        'ru': 'Сначала обновите ссылку с помощью ↻.',
        'uk': 'Спочатку оновіть посилання за допомогою ↻.',
        'be': 'Спачатку абнавіце спасылку з дапамогай ↻.',
        'zh': '请先使用 ↻ 刷新链接。',
    },
    'action_verification_opened': {
        'en': 'A fresh verification link opened in your browser.',
        'ru': 'Свежая ссылка для верификации открыта в браузере.',
        'uk': 'Нове посилання для верифікації відкрито у браузері.',
        'be': 'Свежая спасылка для верыфікацыі адкрыта ў браўзеры.',
        'zh': '新的验证链接已在浏览器中打开。',
    },
    'action_verification_accepted': {
        'en': 'Google accepted the check. Verification is no longer required.',
        'ru': 'Google принял проверку. Верификация больше не требуется.',
        'uk': 'Google прийняв перевірку. Верифікація більше не потрібна.',
        'be': 'Google прыняў праверку. Верыфікацыя больш не патрабуецца.',
        'zh': 'Google 已接受验证。不再需要验证。',
    },
    'action_verified_retry': {
        'en': 'Google accepted the check. Account verified; retry your Claude request.',
        'ru': 'Google принял проверку. Аккаунт верифицирован; повторите запрос Claude.',
        'uk': 'Google прийняв перевірку. Акаунт верифіковано; повторіть запит Claude.',
        'be': 'Google прыняў праверку. Акаўнт верыфікаваны; паўтарыце запыт Claude.',
        'zh': 'Google 已接受验证。账户已验证；请重试 Claude 请求。',
    },
    'action_generic_error': {
        'en': 'Could not complete this action. Try reloading the list.',
        'ru': 'Не удалось выполнить действие. Попробуйте обновить список.',
        'uk': 'Не вдалося виконати дію. Спробуйте оновити список.',
        'be': 'Не атрымалася выканаць дзеянне. Паспрабуйце абнавіць спіс.',
        'zh': '无法完成此操作。请尝试刷新列表。',
    },

    # ── Confirmation dialogs ──────────────────────────────────────────
    'confirm_remove_title': {
        'en': 'Remove account?',
        'ru': 'Удалить аккаунт?',
        'uk': 'Видалити акаунт?',
        'be': 'Выдаліць акаўнт?',
        'zh': '移除账户？',
    },
    'confirm_remove_body': {
        'en': 'Remove {email} from Gemini Accounts?\n\nIts saved sign-in will be deleted and it will no longer be used for new requests. Your Google account will not be deleted. You can add it again by signing in.\n\nAn ongoing request may still finish on this account.',
        'ru': 'Удалить {email} из Gemini Аккаунтов?\n\nСохранённый вход будет удалён, и аккаунт больше не будет использоваться для новых запросов. Ваш аккаунт Google не будет удалён. Вы можете добавить его снова, войдя в систему.\n\nТекущий запрос может завершиться на этом аккаунте.',
        'uk': 'Видалити {email} з Gemini Акаунтів?\n\nЗбережений вхід буде видалено, і акаунт більше не буде використовуватися для нових запитів. Ваш акаунт Google не буде видалено. Ви можете додати його знову, увійшовши в систему.\n\nПоточний запит може завершитися на цьому акаунті.',
        'be': 'Выдаліць {email} з Gemini Акаўнтаў?\n\nЗахаваны ўваход будзе выдалены, і акаўнт больш не будзе выкарыстоўвацца для новых запытаў. Ваш акаўнт Google не будзе выдалены. Вы можаце дадаць яго зноў, увайшоўшы ў сістэму.\n\nБягучы запыт можа завяршыцца на гэтым акаўнце.',
        'zh': '从 Gemini 账户中移除 {email}？\n\n保存的登录信息将被删除，该账户将不再用于新请求。您的 Google 账户不会被删除。您可以重新登录来再次添加。\n\n正在进行的请求可能仍在此账户上完成。',
    },
    'confirm_allow_setup_title': {
        'en': 'Allow application setup?',
        'ru': 'Разрешить настройку приложений?',
        'uk': 'Дозволити налаштування додатків?',
        'be': 'Дазволіць наладку праграм?',
        'zh': '允许应用设置？',
    },
    'confirm_restore_title': {
        'en': 'Restore previous settings?',
        'ru': 'Восстановить прежние настройки?',
        'uk': 'Відновити попередні налаштування?',
        'be': 'Аднавіць папярэднія налады?',
        'zh': '恢复以前的设置？',
    },
    'confirm_restart_title': {
        'en': 'Apply settings now?',
        'ru': 'Применить настройки сейчас?',
        'uk': 'Застосувати налаштування зараз?',
        'be': 'Ужыць налады зараз?',
        'zh': '立即应用设置？',
    },
    'confirm_restart_body': {
        'en': 'Restart running Claude / Codex clients to apply connections? This interrupts current work. Saved sessions are preserved.',
        'ru': 'Перезапустить работающие клиенты Claude / Codex для применения подключений? Текущая работа будет прервана. Сохранённые сессии сохраняются.',
        'uk': 'Перезапустити працюючі клієнти Claude / Codex для застосування підключень? Поточну роботу буде перервано. Збережені сесії зберігаються.',
        'be': 'Перазапусціць працуючыя кліенты Claude / Codex для ўжывання злучэнняў? Бягучая праца будзе перарвана. Захаваныя сесіі захоўваюцца.',
        'zh': '重启运行中的 Claude / Codex 客户端以应用连接？这将中断当前工作。保存的会话将被保留。',
    },
    'confirm_restore_apply_title': {
        'en': 'Apply restoration now?',
        'ru': 'Применить восстановление сейчас?',
        'uk': 'Застосувати відновлення зараз?',
        'be': 'Ужыць аднаўленне зараз?',
        'zh': '立即应用恢复？',
    },

    # ── Diagnostics ───────────────────────────────────────────────────
    'diag_recipient': {
        'en': 'Diagnostic recipient',
        'ru': 'Получатель диагностики',
        'uk': 'Отримувач діагностики',
        'be': 'Атрымальнік дыягностыкі',
        'zh': '诊断接收方',
    },
    'diag_endpoint_prompt': {
        'en': 'HTTPS diagnostic upload endpoint:',
        'ru': 'HTTPS-адрес для отправки диагностики:',
        'uk': 'HTTPS-адреса для надсилання діагностики:',
        'be': 'HTTPS-адрас для адпраўкі дыягностыкі:',
        'zh': 'HTTPS 诊断上传端点：',
    },
    'diag_invalid_url': {
        'en': 'Use an HTTPS URL without embedded credentials.',
        'ru': 'Используйте HTTPS URL без встроенных учётных данных.',
        'uk': 'Використовуйте HTTPS URL без вбудованих облікових даних.',
        'be': 'Выкарыстоўвайце HTTPS URL без убудаваных уліковых даных.',
        'zh': '请使用不含嵌入凭据的 HTTPS URL。',
    },
    'diag_token_prompt': {
        'en': 'Upload access token for {host}:',
        'ru': 'Токен доступа для загрузки на {host}:',
        'uk': 'Токен доступу для завантаження на {host}:',
        'be': 'Токен доступу для загрузкі на {host}:',
        'zh': '{host} 的上传访问令牌：',
    },
    'diag_sent': {
        'en': 'Server accepted the archive (HTTP {status}).',
        'ru': 'Сервер принял архив (HTTP {status}).',
        'uk': 'Сервер прийняв архів (HTTP {status}).',
        'be': 'Сервер прыняў архіў (HTTP {status}).',
        'zh': '服务器已接受存档（HTTP {status}）。',
    },
    'diag_saved': {
        'en': 'Diagnostic log saved',
        'ru': 'Диагностический журнал сохранён',
        'uk': 'Діагностичний журнал збережено',
        'be': 'Дыягнастычны журнал захаваны',
        'zh': '诊断日志已保存',
    },

    # ── Theme / Settings ──────────────────────────────────────────────
    'theme_dark': {
        'en': 'Dark',
        'ru': 'Тёмная',
        'uk': 'Темна',
        'be': 'Цёмная',
        'zh': '深色',
    },
    'theme_light': {
        'en': 'Light',
        'ru': 'Светлая',
        'uk': 'Світла',
        'be': 'Светлая',
        'zh': '浅色',
    },
    'theme_system': {
        'en': 'System',
        'ru': 'Системная',
        'uk': 'Системна',
        'be': 'Сістэмная',
        'zh': '跟随系统',
    },
    'settings_language': {
        'en': 'Language',
        'ru': 'Язык',
        'uk': 'Мова',
        'be': 'Мова',
        'zh': '语言',
    },
    'settings_theme': {
        'en': 'Theme',
        'ru': 'Тема',
        'uk': 'Тема',
        'be': 'Тэма',
        'zh': '主题',
    },

    # ── Tooltips ──────────────────────────────────────────────────────
    'tip_add_account': {
        'en': 'Add a new Google account for quota sharing',
        'ru': 'Добавить новый Google аккаунт для распределения квот',
        'uk': 'Додати новий Google акаунт для розподілу квот',
        'be': 'Дадаць новы Google акаўнт для размеркавання квот',
        'zh': '添加新的 Google 账户以共享配额',
    },
    'tip_model_settings': {
        'en': 'Choose which models to use for Claude and Gemini',
        'ru': 'Выбрать модели для Claude и Gemini',
        'uk': 'Обрати моделі для Claude та Gemini',
        'be': 'Абраць мадэлі для Claude і Gemini',
        'zh': '选择 Claude 和 Gemini 使用的模型',
    },
    'tip_toggle_sidebar': {
        'en': 'Collapse or expand the detail panel',
        'ru': 'Свернуть или развернуть панель подробностей',
        'uk': 'Згорнути або розгорнути панель деталей',
        'be': 'Згарнуць або разгарнуць панэль падрабязнасцей',
        'zh': '折叠或展开详情面板',
    },
    'tip_verify': {
        'en': 'Open Google verification page in browser',
        'ru': 'Открыть страницу верификации Google в браузере',
        'uk': 'Відкрити сторінку верифікації Google у браузері',
        'be': 'Адкрыць старонку верыфікацыі Google у браўзеры',
        'zh': '在浏览器中打开 Google 验证页面',
    },
    'tip_refresh_link': {
        'en': 'Get a fresh verification link from Google',
        'ru': 'Получить новую ссылку верификации от Google',
        'uk': 'Отримати нове посилання верифікації від Google',
        'be': 'Атрымаць новую спасылку верыфікацыі ад Google',
        'zh': '从 Google 获取新的验证链接',
    },
    'tip_copy_link': {
        'en': 'Copy verification link to clipboard',
        'ru': 'Скопировать ссылку верификации в буфер обмена',
        'uk': 'Скопіювати посилання верифікації до буфера обміну',
        'be': 'Скапіяваць спасылку верыфікацыі ў буфер абмену',
        'zh': '将验证链接复制到剪贴板',
    },
    'tip_i_verified': {
        'en': 'Tell the app you completed verification in browser',
        'ru': 'Сообщить приложению, что верификация пройдена в браузере',
        'uk': 'Повідомити додатку, що верифікацію пройдено у браузері',
        'be': 'Паведаміць праграме, што верыфікацыя пройдзена ў браўзеры',
        'zh': '告知应用您已在浏览器中完成验证',
    },
    'tip_use_all': {
        'en': 'Enable automatic routing across all accounts',
        'ru': 'Включить автоматическую маршрутизацию по всем аккаунтам',
        'uk': 'Увімкнути автоматичну маршрутизацію по всіх акаунтах',
        'be': 'Уключыць аўтаматычную маршрутызацыю па ўсіх акаўнтах',
        'zh': '启用所有账户的自动路由',
    },
    'tip_connect_apps': {
        'en': 'Configure Claude Desktop, Codex, or CLI connections',
        'ru': 'Настроить подключения Claude Desktop, Codex или CLI',
        'uk': 'Налаштувати підключення Claude Desktop, Codex або CLI',
        'be': 'Наладзіць злучэнні Claude Desktop, Codex або CLI',
        'zh': '配置 Claude Desktop、Codex 或 CLI 连接',
    },
    'tip_use_only': {
        'en': 'Route all requests through this account only',
        'ru': 'Направлять все запросы только через этот аккаунт',
        'uk': 'Направляти всі запити тільки через цей акаунт',
        'be': 'Накіроўваць усе запыты толькі праз гэты акаўнт',
        'zh': '仅通过此账户路由所有请求',
    },
    'tip_pause_resume': {
        'en': 'Pause or resume this account for routing',
        'ru': 'Приостановить или возобновить этот аккаунт для маршрутизации',
        'uk': 'Призупинити або відновити цей акаунт для маршрутизації',
        'be': 'Прыпыніць або аднавіць гэты акаўнт для маршрутызацыі',
        'zh': '暂停或恢复此账户的路由',
    },
    'tip_remove': {
        'en': 'Remove this account from Gemini Accounts',
        'ru': 'Удалить этот аккаунт из Gemini Аккаунтов',
        'uk': 'Видалити цей акаунт з Gemini Акаунтів',
        'be': 'Выдаліць гэты акаўнт з Gemini Акаўнтаў',
        'zh': '从 Gemini 账户中移除此账户',
    },
    'tip_save_label': {
        'en': 'Save a custom display name for this account',
        'ru': 'Сохранить пользовательское имя для этого аккаунта',
        'uk': 'Зберегти користувацьке ім\'я для цього акаунта',
        'be': 'Захаваць карыстальніцкае імя для гэтага акаўнта',
        'zh': '为此账户保存自定义显示名称',
    },
    'tip_theme_toggle': {
        'en': 'Switch between light and dark themes',
        'ru': 'Переключить между светлой и тёмной темами',
        'uk': 'Перемкнути між світлою та темною темами',
        'be': 'Пераключыць паміж светлай і цёмнай тэмамі',
        'zh': '在浅色和深色主题之间切换',
    },
    'tip_language': {
        'en': 'Change interface language',
        'ru': 'Сменить язык интерфейса',
        'uk': 'Змінити мову інтерфейсу',
        'be': 'Змяніць мову інтэрфейсу',
        'zh': '更改界面语言',
    },

    # ── Verification buttons ──────────────────────────────────────────
    'btn_verify': {
        'en': 'Verify',
        'ru': 'Верифицировать',
        'uk': 'Верифікувати',
        'be': 'Верыфікаваць',
        'zh': '验证',
    },
    'btn_i_verified': {
        'en': 'I verified',
        'ru': 'Я прошёл верификацию',
        'uk': 'Я пройшов верифікацію',
        'be': 'Я прайшоў верыфікацыю',
        'zh': '我已验证',
    },

    # ── Activity / event labels ───────────────────────────────────────
    'event_switch': {
        'en': 'SWITCH',
        'ru': 'ПЕРЕКЛЮЧЕНИЕ',
        'uk': 'ПЕРЕМИКАННЯ',
        'be': 'ПЕРАКЛЮЧЭННЕ',
        'zh': '切换',
    },
    'event_error': {
        'en': 'ERROR',
        'ru': 'ОШИБКА',
        'uk': 'ПОМИЛКА',
        'be': 'ПАМЫЛКА',
        'zh': '错误',
    },
    'event_response': {
        'en': 'RESPONSE',
        'ru': 'ОТВЕТ',
        'uk': 'ВІДПОВІДЬ',
        'be': 'АДКАЗ',
        'zh': '响应',
    },
    'activity_proxy_stats': {
        'en': 'Proxy since startup: {success} successful / {failed} errors',
        'ru': 'Прокси с запуска: {success} успешных / {failed} ошибок',
        'uk': 'Проксі з запуску: {success} успішних / {failed} помилок',
        'be': 'Проксі з запуску: {success} паспяховых / {failed} памылак',
        'zh': '代理启动以来: {success} 次成功 / {failed} 次错误',
    },
    'activity_observed': {
        'en': 'Observed: {count} attempts • {tokens} tokens • average {avg} s',
        'ru': 'Зафиксировано: {count} попыток • {tokens} токенов • среднее {avg} с',
        'uk': 'Зафіксовано: {count} спроб • {tokens} токенів • середнє {avg} с',
        'be': 'Зафіксавана: {count} спроб • {tokens} токенаў • сярэдняе {avg} с',
        'zh': '观察到: {count} 次尝试 • {tokens} 个令牌 • 平均 {avg} 秒',
    },
    'activity_waiting_restricted': {
        'en': 'Waiting / restricted',
        'ru': 'Ожидание / ограничен',
        'uk': 'Очікування / обмежено',
        'be': 'Чаканне / абмежаваны',
        'zh': '等待中 / 受限',
    },
    'activity_retry_in': {
        'en': 'next provider retry in {time}',
        'ru': 'следующая попытка провайдера через {time}',
        'uk': 'наступна спроба провайдера через {time}',
        'be': 'наступная спроба правайдера праз {time}',
        'zh': '下次提供商重试在 {time}',
    },
    'proxy_unreachable': {
        'en': 'Cannot reach the proxy. Showing cached data.',
        'ru': 'Не удаётся связаться с прокси. Показаны кешированные данные.',
        'uk': 'Не вдається з\'єднатися з проксі. Показано кешовані дані.',
        'be': 'Не атрымліваецца злучыцца з проксі. Паказаны кэшаваныя даныя.',
        'zh': '无法连接代理。显示缓存数据。',
    },

    # ── Misc ──────────────────────────────────────────────────────────
    'google_account': {
        'en': 'Google account',
        'ru': 'Google аккаунт',
        'uk': 'Google акаунт',
        'be': 'Google акаўнт',
        'zh': 'Google 账户',
    },
    'unknown_account': {
        'en': 'Unknown account',
        'ru': 'Неизвестный аккаунт',
        'uk': 'Невідомий акаунт',
        'be': 'Невядомы акаўнт',
        'zh': '未知账户',
    },
    'already_running': {
        'en': 'Gemini Accounts is already open. Find its window in the taskbar.',
        'ru': 'Gemini Аккаунты уже открыты. Найдите окно на панели задач.',
        'uk': 'Gemini Акаунти вже відкриті. Знайдіть вікно на панелі задач.',
        'be': 'Gemini Акаўнты ўжо адкрыты. Знайдзіце акно на панэлі задач.',
        'zh': 'Gemini 账户已打开。请在任务栏中找到其窗口。',
    },
    'quota_cached_data': {
        'en': 'Showing the latest cached data.',
        'ru': 'Показаны последние кешированные данные.',
        'uk': 'Показано останні кешовані дані.',
        'be': 'Паказаны апошнія кэшаваныя даныя.',
        'zh': '显示最新缓存数据。',
    },
    'quota_load_error': {
        'en': 'Could not load quotas. Try again later.',
        'ru': 'Не удалось загрузить квоты. Попробуйте позже.',
        'uk': 'Не вдалося завантажити квоти. Спробуйте пізніше.',
        'be': 'Не атрымалася загрузіць квоты. Паспрабуйце пазней.',
        'zh': '无法加载配额。请稍后重试。',
    },
    'setup_failed': {
        'en': 'Setup failed: {error}',
        'ru': 'Ошибка настройки: {error}',
        'uk': 'Помилка налаштування: {error}',
        'be': 'Памылка наладкі: {error}',
        'zh': '设置失败: {error}',
    },
}
# fmt: on

# Desktop controls and status messages are translated at the display boundary.
_strings.update({
    'mode_count_hint': dict(en='This counts accounts enabled in the pool. Access is checked separately for each model.', ru='Это число включённых аккаунтов в пуле. Доступ проверяется отдельно для каждой модели.', uk='Це кількість увімкнених акаунтів у пулі. Доступ перевіряється окремо для кожної моделі.', be='Гэта колькасць уключаных акаўнтаў у пуле. Доступ правяраецца асобна для кожнай мадэлі.', zh='此数字表示池中已启用的账户数。每个模型的访问权限分别检查。'),
    'chk_autostart': dict(en='Start with Windows', ru='Запускать с Windows', uk='Запускати з Windows', be='Запускаць з Windows', zh='随 Windows 启动'),
    'btn_mini_mode': dict(en='Mini window', ru='Мини-окно', uk='Міні-вікно', be='Міні-акно', zh='迷你窗口'),
    'btn_full_mode': dict(en='Full window', ru='Полное окно', uk='Повне вікно', be='Поўнае акно', zh='完整窗口'),
    'tip_autostart': dict(en='Open the app automatically when you sign in to Windows.', ru='Открывать приложение при входе в Windows.', uk='Відкривати застосунок під час входу у Windows.', be='Адкрываць праграму пры ўваходзе ў Windows.', zh='登录 Windows 时自动打开应用。'),
    'tip_mini_mode': dict(en='Show only the accounts in a small window above other windows. Click again to restore the full view.', ru='Показать только аккаунты в небольшом окне поверх остальных. Повторное нажатие вернёт полное окно.', uk='Показати лише акаунти в невеликому вікні поверх інших. Натисніть ще раз, щоб повернути повний вигляд.', be='Паказаць толькі акаўнты ў невялікім акне над іншымі. Паўторны націск верне поўнае акно.', zh='在置顶的小窗口中仅显示账户。再次点击恢复完整视图。'),
    'tip_save_diag': dict(en='Save a diagnostics archive to a folder you choose.', ru='Сохранить архив диагностики в выбранную папку.', uk='Зберегти архів діагностики у вибрану папку.', be='Захаваць архіў дыягностыкі ў выбраную папку.', zh='将诊断压缩包保存到所选文件夹。'),
    'tip_send_diag': dict(en='Review the diagnostics before sending them to the developer.', ru='Просмотреть диагностику перед отправкой разработчику.', uk='Переглянути діагностику перед надсиланням розробнику.', be='Праглядзець дыягностыку перад адпраўкай распрацоўшчыку.', zh='发送给开发者之前查看诊断信息。'),
    'tip_check_updates': dict(en='Check whether a new release is available.', ru='Проверить наличие новой версии программы.', uk='Перевірити наявність нової версії програми.', be='Праверыць наяўнасць новай версіі праграмы.', zh='检查是否有新版本。'),
    'tray_show': dict(en='Open window', ru='Открыть окно', uk='Відкрити вікно', be='Адкрыць акно', zh='打开窗口'),
    'tray_exit': dict(en='Exit', ru='Выйти', uk='Вийти', be='Выйсці', zh='退出'),
    'tray_minimized_title': dict(en='Gemini Accounts is in the tray', ru='Gemini Аккаунты свёрнуты в трей', uk='Gemini Акаунти згорнуто в трей', be='Gemini Акаўнты згорнуты ў трэй', zh='Gemini 账户已最小化到托盘'),
    'tray_minimized_text': dict(en='Double-click the tray icon to open the window.', ru='Дважды нажмите на значок в трее, чтобы открыть окно.', uk='Двічі натисніть на значок у треї, щоб відкрити вікно.', be='Двойчы націсніце на значок у трэі, каб адкрыць акно.', zh='双击托盘图标可打开窗口。'),
    'vpn_status': dict(en='VPN connection', ru='VPN-соединение', uk='VPN-з’єднання', be='VPN-злучэнне', zh='VPN 连接'),
    'vpn_warning_banner': dict(en='No active VPN adapter detected. Check your connection if requests fail.', ru='Активный VPN-адаптер не обнаружен. Если запросы не проходят, проверьте подключение.', uk='Активний VPN-адаптер не виявлено. Якщо запити не проходять, перевірте з’єднання.', be='Актыўны VPN-адаптар не знойдзены. Калі запыты не праходзяць, праверце злучэнне.', zh='未检测到活动的 VPN 适配器。如果请求失败，请检查连接。'),
    'vpn_connected_msg': dict(en='An active VPN adapter was detected.', ru='Обнаружен активный VPN-адаптер.', uk='Виявлено активний VPN-адаптер.', be='Знойдзены актыўны VPN-адаптар.', zh='已检测到活动的 VPN 适配器。'),
    'vpn_disconnected_msg': dict(en='No active VPN adapter detected. Check your connection.', ru='Активный VPN-адаптер не обнаружен. Проверьте подключение.', uk='Активний VPN-адаптер не виявлено. Перевірте з’єднання.', be='Актыўны VPN-адаптар не знойдзены. Праверце злучэнне.', zh='未检测到活动的 VPN 适配器。请检查连接。'),
    'account_connection_error': dict(en='Account connection error', ru='Ошибка подключения аккаунта', uk='Помилка підключення акаунта', be='Памылка падключэння акаўнта', zh='账户连接错误'),
    'account_cached_quota': dict(en='Cached quotas · access not confirmed', ru='Квоты из кэша · доступ не подтверждён', uk='Квоти з кешу · доступ не підтверджено', be='Квоты з кэша · доступ не пацверджаны', zh='缓存配额 · 尚未确认访问权限'),
    'account_quota_hint': dict(en='Quota bars show the reported balance, not a successful model request.', ru='Полоски показывают полученные квоты, а не успешный запрос к модели.', uk='Смужки показують отримані квоти, а не успішний запит до моделі.', be='Палоскі паказваюць атрыманыя квоты, а не паспяховы запыт да мадэлі.', zh='配额条显示报告的余额，并不表示模型请求成功。'),
    'account_enabled_status': dict(en='Enabled · availability depends on the model', ru='Включён · доступность зависит от модели', uk='Увімкнено · доступність залежить від моделі', be='Уключаны · даступнасць залежыць ад мадэлі', zh='已启用 · 可用性取决于模型'),
    'activity_model_retry': dict(en='{model}: retry in {time}', ru='{model}: повтор через {time}', uk='{model}: повтор через {time}', be='{model}: паўтор праз {time}', zh='{model}：{time} 后重试'),
    'activity_all_models': dict(en='All models', ru='Все модели', uk='Усі моделі', be='Усе мадэлі', zh='所有模型'),
    'activity_last': dict(en='last: {time}', ru='последний: {time}', uk='останній: {time}', be='апошні: {time}', zh='最近：{time}'),
    'activity_strategy': dict(en='Strategy: {strategy}', ru='Стратегия: {strategy}', uk='Стратегія: {strategy}', be='Стратэгія: {strategy}', zh='策略：{strategy}'),
    'unit_day': dict(en='d', ru='д', uk='д', be='д', zh='天'),
    'unit_hour': dict(en='h', ru='ч', uk='г', be='г', zh='小时'),
    'unit_minute': dict(en='m', ru='м', uk='хв', be='хв', zh='分钟'),
    'period_5h': dict(en='5h', ru='5ч', uk='5г', be='5г', zh='5时'),
    'period_weekly': dict(en='1w', ru='1н', uk='1т', be='1т', zh='1周'),
    'rank_exhausted': dict(en='Quota exhausted; waiting for all blocking windows to reset', ru='Квота исчерпана; ожидание сброса всех ограничивающих окон', uk='Квоту вичерпано; очікування скидання всіх обмежувальних вікон', be='Квота вычарпана; чаканне скіду ўсіх абмежавальных вокнаў', zh='配额已耗尽；等待所有限制窗口重置'),
    'rank_reset_unknown': dict(en='Reset reached or unknown; fresh quota data required', ru='Срок сброса наступил или неизвестен; нужно обновить квоты', uk='Час скидання настав або невідомий; потрібно оновити квоти', be='Час скіду настаў або невядомы; трэба абнавіць квоты', zh='重置时间已到或未知；需要更新配额数据'),
    'rank_no_data': dict(en='No fresh complete quota data', ru='Нет свежих полных данных о квотах', uk='Немає свіжих повних даних про квоти', be='Няма свежых поўных даных пра квоты', zh='没有完整的最新配额数据'),
    'rank_available': dict(en='Quota available; nearest 5h reset', ru='Квота есть; ближайший сброс окна 5ч', uk='Квота є; найближче скидання вікна 5г', be='Квота ёсць; найбліжэйшы скід акна 5г', zh='配额可用；最近的 5 小时窗口重置'),
    'rank_available_unknown': dict(en='Quota available; 5h reset time unknown', ru='Квота есть; время сброса окна 5ч неизвестно', uk='Квота є; час скидання вікна 5г невідомий', be='Квота ёсць; час скіду акна 5г невядомы', zh='配额可用；5 小时窗口重置时间未知'),
    'rank_restricted': dict(en='Proxy temporarily excluded this account for this group', ru='Прокси временно исключил аккаунт для этой группы моделей', uk='Проксі тимчасово виключив акаунт для цієї групи моделей', be='Проксі часова выключыў акаўнт для гэтай групы мадэляў', zh='代理暂时将此账户排除在该模型组之外'),
    'confirm_model_files': dict(en='Model choices will change in:\n\n{paths}\n\nAllow changes?', ru='Модели будут изменены в файлах:\n\n{paths}\n\nРазрешить изменения?', uk='Моделі буде змінено у файлах:\n\n{paths}\n\nДозволити зміни?', be='Мадэлі будуць зменены ў файлах:\n\n{paths}\n\nДазволіць змены?', zh='将在以下文件中更改模型选择：\n\n{paths}\n\n允许更改吗？'),
    'confirm_config_files': dict(en='Configuration files:\n\n{paths}\n\nAllow changes?', ru='Файлы конфигурации:\n\n{paths}\n\nРазрешить изменения?', uk='Файли конфігурації:\n\n{paths}\n\nДозволити зміни?', be='Файлы канфігурацыі:\n\n{paths}\n\nДазволіць змены?', zh='配置文件：\n\n{paths}\n\n允许更改吗？'),
    'confirm_restore_body': dict(en='Restore original configurations?', ru='Восстановить исходные настройки приложений?', uk='Відновити початкові налаштування застосунків?', be='Аднавіць зыходныя налады праграм?', zh='恢复原始配置吗？'),
    'event_received': dict(en='Response received', ru='Ответ получен', uk='Відповідь отримано', be='Адказ атрыманы', zh='已收到响应'),
    'event_changed': dict(en='The model account changed; the proxy did not report the exact reason', ru='Аккаунт модели сменился; прокси не сообщил точную причину', uk='Акаунт моделі змінився; проксі не повідомив точну причину', be='Акаўнт мадэлі змяніўся; проксі не паведаміў дакладную прычыну', zh='模型账户已更改；代理未报告确切原因'),
    'event_rate_limit': dict(en='Google 429: temporary request rate limit; waiting to retry', ru='Google 429: временное ограничение частоты запросов; ожидание повтора', uk='Google 429: тимчасове обмеження частоти запитів; очікування повтору', be='Google 429: часовае абмежаванне частаты запытаў; чаканне паўтору', zh='Google 429：暂时限制请求频率；等待重试'),
    'event_capacity': dict(en='Google 429: model capacity unavailable; waiting to retry', ru='Google 429: модель перегружена; ожидание повтора', uk='Google 429: модель перевантажена; очікування повтору', be='Google 429: мадэль перагружана; чаканне паўтору', zh='Google 429：模型容量不足；等待重试'),
    'event_exhausted': dict(en='Google 429: quota exhausted for this model', ru='Google 429: квота этой модели исчерпана', uk='Google 429: квоту цієї моделі вичерпано', be='Google 429: квота гэтай мадэлі вычарпана', zh='Google 429：此模型的配额已耗尽'),
    'event_restricted': dict(en='Google 429: provider restricted this model; exact cause unavailable', ru='Google 429: провайдер ограничил эту модель; точная причина неизвестна', uk='Google 429: провайдер обмежив цю модель; точна причина невідома', be='Google 429: правайдар абмежаваў гэтую мадэль; дакладная прычына невядомая', zh='Google 429：提供商限制了此模型；确切原因未知'),
    'event_verification': dict(en='Google requires account verification; this is not a quota error', ru='Google требует подтверждения аккаунта; это не ошибка квоты', uk='Google вимагає підтвердження акаунта; це не помилка квоти', be='Google патрабуе пацверджання акаўнта; гэта не памылка квоты', zh='Google 要求验证账户；这不是配额错误'),
    'event_retry_account': dict(en='Retry using another account: {reason}', ru='Повтор через другой аккаунт: {reason}', uk='Повтор через інший акаунт: {reason}', be='Паўтор праз іншы акаўнт: {reason}', zh='使用其他账户重试：{reason}'),
    'event_denied': dict(en='Google returned {code}: access denied', ru='Google вернул {code}: доступ запрещён', uk='Google повернув {code}: доступ заборонено', be='Google вярнуў {code}: доступ забаронены', zh='Google 返回 {code}：访问被拒绝'),
    'event_service_error': dict(en='Service error {code}', ru='Ошибка сервиса {code}', uk='Помилка сервісу {code}', be='Памылка сэрвісу {code}', zh='服务错误 {code}'),
    'event_request_error': dict(en='Request error {code}', ru='Ошибка запроса {code}', uk='Помилка запиту {code}', be='Памылка запыту {code}', zh='请求错误 {code}'),
    'event_no_status': dict(en='Request failed without a status code', ru='Запрос завершился ошибкой без кода ответа', uk='Запит завершився помилкою без коду відповіді', be='Запыт завяршыўся памылкай без кода адказу', zh='请求失败，未返回状态码'),
    'event_metrics': dict(en='{seconds} s • {tokens} tokens', ru='{seconds} с • {tokens} токенов', uk='{seconds} с • {tokens} токенів', be='{seconds} с • {tokens} токенаў', zh='{seconds} 秒 • {tokens} 个令牌'),
})


def display_reason(reason):
    """Translate known backend captions without modifying persisted diagnostics."""
    reason = reason or ''
    for key in ('rank_exhausted', 'rank_reset_unknown', 'rank_no_data', 'rank_available',
                'rank_available_unknown', 'rank_restricted', 'event_received', 'event_changed',
                'event_rate_limit', 'event_capacity', 'event_exhausted', 'event_restricted',
                'event_verification', 'event_no_status'):
        if reason == _strings[key]['en']:
            return tr(key)
    prefix = 'Retry using another account: '
    if reason.startswith(prefix):
        return tr('event_retry_account', reason=display_reason(reason[len(prefix):]))
    for prefix, key in (('Service error ', 'event_service_error'), ('Request error ', 'event_request_error')):
        if reason.startswith(prefix) and reason[len(prefix):].isdigit():
            return tr(key, code=reason[len(prefix):])
    if reason.startswith('Google returned ') and reason.endswith(': access denied'):
        code = reason[len('Google returned '):].split(':')[0]
        if code.isdigit():
            return tr('event_denied', code=code)
    return reason


def tr(key, **kwargs):
    """Return the translated string for *key* in the active language.

    Supports ``{placeholder}`` substitution via keyword arguments.
    Falls back to English if a translation is missing, then to the raw key.
    """
    entry = _strings.get(key, {})
    text = entry.get(_current, entry.get('en', key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def set_language(code):
    """Switch the active language.  *code* must be a key from LANGUAGES."""
    global _current
    if code in LANGUAGES:
        _current = code


def current_language():
    """Return the active language code (e.g. ``'ru'``)."""
    return _current
