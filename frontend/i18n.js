(function() {
    const STORAGE_KEY = 'yuni_lang';
    const DEFAULT_LANG = 'zh-CN';
    const LANGS = [
        { code: 'zh-CN', label: '简' },
        { code: 'zh-TW', label: '繁' },
        { code: 'en',    label: 'EN' }
    ];

    function getLang() {
        return localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;
    }

    function setLang(code) {
        localStorage.setItem(STORAGE_KEY, code);
        applyTranslations();
        updateSwitcherUI();
        document.documentElement.lang = code;
        window.dispatchEvent(new CustomEvent('yuni-lang-changed', { detail: code }));
    }

    function applyTranslations() {
        const lang = getLang();
        const dict = (window.PAGE_TRANSLATIONS || {})[lang] || {};

        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (dict[key] !== undefined) {
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                    el.placeholder = dict[key];
                } else if (el.tagName === 'OPTION') {
                    el.textContent = dict[key];
                } else {
                    el.innerHTML = dict[key];
                }
            }
        });

        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            if (dict[key] !== undefined) {
                el.title = dict[key];
            }
        });

        if (dict['_title']) {
            document.title = dict['_title'];
        }
    }

    function createSwitcher() {
        const lang = getLang();
        const wrapper = document.createElement('div');
        wrapper.id = 'lang-switcher';
        wrapper.className = 'flex items-center gap-1';
        wrapper.style.cssText = 'font-size:13px;';

        LANGS.forEach((l, i) => {
            const btn = document.createElement('button');
            btn.textContent = l.label;
            btn.setAttribute('data-lang', l.code);
            btn.className = l.code === lang
                ? 'px-2 py-1 rounded text-white font-medium'
                : 'px-2 py-1 rounded text-slate-500 hover:text-slate-800 transition-colors';
            if (l.code === lang) {
                btn.style.background = '#6A3AB7';
            }
            btn.onclick = () => setLang(l.code);
            wrapper.appendChild(btn);

            if (i < LANGS.length - 1) {
                const sep = document.createElement('span');
                sep.textContent = '|';
                sep.className = 'text-slate-300';
                wrapper.appendChild(sep);
            }
        });

        return wrapper;
    }

    function updateSwitcherUI() {
        const switcher = document.getElementById('lang-switcher');
        if (!switcher) return;
        const lang = getLang();
        switcher.querySelectorAll('button[data-lang]').forEach(btn => {
            const code = btn.getAttribute('data-lang');
            if (code === lang) {
                btn.className = 'px-2 py-1 rounded text-white font-medium';
                btn.style.background = '#6A3AB7';
            } else {
                btn.className = 'px-2 py-1 rounded text-slate-500 hover:text-slate-800 transition-colors';
                btn.style.background = '';
            }
        });
    }

    function injectSwitcher() {
        const nav = document.querySelector('nav');
        if (!nav) return;

        const row = nav.querySelector('.flex.justify-between') ||
                     nav.querySelector('.h-16.flex') ||
                     nav.querySelector('.flex');
        if (!row) return;

        const switcher = createSwitcher();

        const lastChild = row.lastElementChild;
        if (lastChild) {
            const wrapper = document.createElement('div');
            wrapper.className = 'flex items-center gap-4';
            row.insertBefore(wrapper, lastChild);
            wrapper.appendChild(switcher);
            wrapper.appendChild(lastChild);
        } else {
            row.appendChild(switcher);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        injectSwitcher();
        applyTranslations();
    });

    window.YuniI18n = { getLang, setLang, applyTranslations };
})();
