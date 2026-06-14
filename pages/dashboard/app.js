(function () {
  // ══════════════════════════════════════════════════════════════════════════
  // 共享工具
  // ══════════════════════════════════════════════════════════════════════════

  // AstrBot 可能在 iframe HTML 末尾注入 bridge；等待窗口只覆盖注入竞态，超时后显式报错。
  var BRIDGE_WAIT_ATTEMPTS = 50;
  var BRIDGE_WAIT_INTERVAL_MS = 100;
  var toastTimer = null;

  function qs(sel, ctx) { return (ctx || document).querySelector(sel); }
  function qsa(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function apiResult(result) {
    if (result && result.success === false) throw new Error(result.error || '请求失败');
    return result || {};
  }

  function getBridge() {
    return window.AstrBotPluginPage || null;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function waitForBridge() {
    var found = getBridge();
    if (found) return Promise.resolve(found);

    var attempt = 0;
    function poll() {
      var current = getBridge();
      if (current) return Promise.resolve(current);

      attempt += 1;
      if (attempt >= BRIDGE_WAIT_ATTEMPTS) {
        return Promise.reject(new Error('请从 AstrBot Plugin Pages 打开此页面'));
      }
      return sleep(BRIDGE_WAIT_INTERVAL_MS).then(poll);
    }
    return poll();
  }

  function bridgeReady() {
    return waitForBridge().then(function (current) {
      if (typeof current.ready !== 'function') {
        throw new Error('Plugin Pages bridge 不支持 ready');
      }
      return current.ready().then(function () {
        return current;
      });
    });
  }

  function apiGet(path, params) {
    return bridgeReady().then(function (current) {
      if (typeof current.apiGet !== 'function') throw new Error('Plugin Pages bridge 不支持 apiGet');
      return current.apiGet(path, params);
    });
  }

  function apiPost(path, payload) {
    return bridgeReady().then(function (current) {
      if (typeof current.apiPost !== 'function') throw new Error('Plugin Pages bridge 不支持 apiPost');
      return current.apiPost(path, payload);
    });
  }

  function createStore(initial) {
    return new Proxy(initial, {
      set: function (target, key, val) {
        target[key] = val;
        return true;
      },
      get: function (target, key) { return target[key]; },
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 全局状态
  // ══════════════════════════════════════════════════════════════════════════

  var globalStore = createStore({
    activeTab: 'sessionConfig',
    toast: { show: false, type: 'success', message: '' },
  });

  globalStore.showToast = function (message, type) {
    type = type || 'success';
    if (toastTimer) window.clearTimeout(toastTimer);
    globalStore.toast = { show: true, type: type, message: message };
    renderToast();
    toastTimer = window.setTimeout(function () {
      globalStore.toast = { show: false, type: 'success', message: '' };
      renderToast();
    }, 2600);
  };

  function renderToast() {
    var el = qs('#toast');
    if (!el) return;
    el.className = 'toast' + (globalStore.toast.type === 'error' ? ' error' : '');
    el.style.display = globalStore.toast.show ? '' : 'none';
    el.textContent = globalStore.toast.message;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 导航逻辑
  // ══════════════════════════════════════════════════════════════════════════

  function switchTab(tab) {
    globalStore.activeTab = tab;
    renderTabPanels();
    closeMobileNav();
    // 懒加载
    if (tab === 'sessionConfig' && !sessionModule.loaded) sessionModule.init();
    if (tab === 'accessControl' && !accessModule.loaded) accessModule.init();
  }

  function renderTabPanels() {
    qsa('.tab-panel').forEach(function (panel) {
      panel.classList.toggle('active', panel.id === 'tab-' + globalStore.activeTab);
    });
    qsa('.nav-item').forEach(function (item) {
      item.classList.toggle('active', item.dataset.tab === globalStore.activeTab);
    });
  }

  function closeMobileNav() {
    qs('#nav-sidebar').classList.remove('open');
    qs('#nav-overlay').classList.remove('visible');
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 会话配置模块
  // ══════════════════════════════════════════════════════════════════════════

  var sessionModule = {
    loaded: false,
    store: null,

    init: function () {
      if (this.loaded) return;
      this.loaded = true;

      this.store = createStore({
        loading: false,
        keys: [],
        sessions: [],
        globalValues: {},
        form: this.emptyForm(),
      });

      this.bindEvents();
      this.reload();
    },

    emptyForm: function () {
      return { session_id: '', session_type: 'group', display_name: '', overrides: {} };
    },

    reload: function () {
      var self = this;
      var s = this.store;
      s.loading = true;
      self.renderAll();
      apiGet('session-config').then(apiResult).then(function (result) {
        s.keys = result.keys || [];
        s.sessions = result.sessions || [];
        s.globalValues = result.global || {};
        if (s.form.session_id) {
          var sel = s.sessions.find(function (x) { return x.session_id === s.form.session_id; });
          if (sel) self.selectSession(sel);
        }
      }).catch(function (err) {
        globalStore.showToast(err.message || '加载会话配置失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderAll();
      });
    },

    newSession: function () {
      this.store.form = this.emptyForm();
      this.renderAll();
    },

    selectSession: function (session) {
      this.store.form = {
        session_id: session.session_id || '',
        session_type: session.session_type || 'group',
        display_name: session.display_name || '',
        overrides: Object.assign({}, session.overrides || {}),
      };
      this.renderAll();
    },

    hasOverride: function (key) {
      return Object.prototype.hasOwnProperty.call(this.store.form.overrides, key);
    },

    toggleOverride: function (key, enabled) {
      if (enabled) {
        this.store.form.overrides[key] = this.effectiveValue(key);
      } else {
        delete this.store.form.overrides[key];
      }
      this.renderKeyCards();
    },

    effectiveValue: function (key) {
      return this.hasOverride(key) ? this.store.form.overrides[key] : this.store.globalValues[key];
    },

    displayValue: function (value) {
      if (value === true) return '启用';
      if (value === false) return '禁用';
      if (value === '' || value === undefined || value === null) return '空';
      return String(value);
    },

    save: function () {
      var self = this;
      var s = this.store;
      if (!s.form.session_id.trim()) {
        globalStore.showToast('session_id 不能为空', 'error');
        return;
      }
      s.loading = true;
      self.renderAll();
      apiPost('session-config/upsert', s.form).then(apiResult).then(function (result) {
        self.selectSession(result.data || s.form);
        return self.reload();
      }).then(function () {
        globalStore.showToast('已保存');
      }).catch(function (err) {
        globalStore.showToast(err.message || '保存失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderAll();
      });
    },

    clearAll: function () {
      var self = this;
      var s = this.store;
      if (!s.form.session_id) return;
      s.loading = true;
      self.renderAll();
      apiPost('session-config/clear', s.form).then(apiResult).then(function (result) {
        self.selectSession(result.data || s.form);
        return self.reload();
      }).then(function () {
        globalStore.showToast('已清空覆盖');
      }).catch(function (err) {
        globalStore.showToast(err.message || '清空失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderAll();
      });
    },

    deleteSession: function () {
      var self = this;
      var s = this.store;
      if (!s.form.session_id) return;
      s.loading = true;
      self.renderAll();
      apiPost('session-config/delete', { session_id: s.form.session_id }).then(apiResult).then(function () {
        s.form = self.emptyForm();
        return self.reload();
      }).then(function () {
        globalStore.showToast('已删除');
      }).catch(function (err) {
        globalStore.showToast(err.message || '删除失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderAll();
      });
    },

    // ── 渲染 ──────────────────────────────────────────────────────────────

    renderAll: function () {
      this.renderSessions();
      this.renderFormFields();
      this.renderButtons();
      this.renderKeyCards();
    },

    renderSessions: function () {
      var self = this;
      var list = qs('#session-list');
      list.innerHTML = '';
      if (this.store.sessions.length === 0) {
        list.innerHTML = '<div class="hint">暂无会话配置</div>';
        return;
      }
      this.store.sessions.forEach(function (session) {
        var btn = document.createElement('button');
        btn.className = 'session-card' + (self.store.form.session_id === session.session_id ? ' active' : '');
        btn.innerHTML =
          '<div class="session-title">' + escHtml(session.display_name || session.session_id) + '</div>' +
          '<div class="session-meta">' + escHtml(session.session_type) + ' · ' + Object.keys(session.overrides || {}).length + ' 项覆盖</div>';
        btn.addEventListener('click', function () { self.selectSession(session); });
        list.appendChild(btn);
      });
    },

    renderFormFields: function () {
      var sidInput = qs('#field-session-id');
      var stypeSel = qs('#field-session-type');
      var dnameInput = qs('#field-display-name');
      if (sidInput) sidInput.value = this.store.form.session_id;
      if (stypeSel) stypeSel.value = this.store.form.session_type;
      if (dnameInput) dnameInput.value = this.store.form.display_name;
    },

    renderButtons: function () {
      var s = this.store;
      var hasSession = !!s.form.session_id;
      qsa('[data-action^="sc-"]').forEach(function (btn) {
        var a = btn.dataset.action;
        if (a === 'sc-reload') { btn.disabled = !!s.loading; return; }
        if (a === 'sc-delete') { btn.disabled = !hasSession || !!s.loading; return; }
        if (a === 'sc-save') { btn.disabled = !!s.loading; return; }
        if (a === 'sc-clear') { btn.disabled = !hasSession || !!s.loading; return; }
      });
    },

    renderKeyCards: function () {
      var self = this;
      var keysEl = qs('#key-list');
      keysEl.innerHTML = '';
      this.store.keys.forEach(function (item) {
        var hasOv = self.hasOverride(item.key);
        var effVal = self.effectiveValue(item.key);
        keysEl.appendChild(self.buildKeyCard(item, hasOv, effVal));
      });
    },

    buildKeyCard: function (item, hasOv, effVal) {
      var self = this;
      var card = document.createElement('div');
      card.className = 'key-card';

      var labelDiv = document.createElement('div');
      labelDiv.innerHTML = '<strong>' + escHtml(item.label) + '</strong><div class="key-name">' + escHtml(item.key) + '</div>';
      card.appendChild(labelDiv);

      var toggleDiv = document.createElement('div');
      toggleDiv.className = 'toggle';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = hasOv;
      cb.addEventListener('change', function (e) { self.toggleOverride(item.key, e.target.checked); });
      toggleDiv.appendChild(cb);
      toggleDiv.appendChild(document.createTextNode('会话覆盖'));
      card.appendChild(toggleDiv);

      var globalDiv = document.createElement('div');
      globalDiv.innerHTML = '<div class="key-name">全局配置</div><strong>' + escHtml(self.displayValue(self.store.globalValues[item.key])) + '</strong>';
      card.appendChild(globalDiv);

      var effDiv = document.createElement('div');
      effDiv.innerHTML = '<div class="key-name">生效值</div><strong>' + escHtml(self.displayValue(effVal)) + '</strong>';
      card.appendChild(effDiv);

      if (hasOv) {
        var inputRow = document.createElement('div');
        inputRow.className = 'key-override-row';
        if (item.type === 'enum') {
          var sel = document.createElement('select');
          sel.className = 'select-input';
          item.options.forEach(function (opt) {
            var optEl = document.createElement('option');
            optEl.value = opt;
            optEl.textContent = opt;
            if (opt === self.store.form.overrides[item.key]) optEl.selected = true;
            sel.appendChild(optEl);
          });
          sel.addEventListener('change', function (e) {
            self.store.form.overrides[item.key] = e.target.value;
            self.renderKeyCards();
          });
          inputRow.appendChild(sel);
        } else if (item.type === 'bool') {
          var boolDiv = document.createElement('label');
          boolDiv.className = 'toggle';
          var boolCb = document.createElement('input');
          boolCb.type = 'checkbox';
          boolCb.checked = !!self.store.form.overrides[item.key];
          boolCb.addEventListener('change', function (e) {
            self.store.form.overrides[item.key] = e.target.checked;
            self.renderKeyCards();
          });
          boolDiv.appendChild(boolCb);
          boolDiv.appendChild(document.createTextNode(self.displayValue(self.store.form.overrides[item.key])));
          inputRow.appendChild(boolDiv);
        } else {
          var inp = document.createElement('input');
          inp.className = 'search-input';
          inp.value = self.store.form.overrides[item.key] != null ? self.store.form.overrides[item.key] : '';
          inp.addEventListener('input', function (e) { self.store.form.overrides[item.key] = e.target.value; });
          inputRow.appendChild(inp);
        }
        card.appendChild(inputRow);
      }

      return card;
    },

    bindEvents: function () {
      var self = this;
      qs('#btn-new').addEventListener('click', function () { self.newSession(); });
      qsa('[data-action^="sc-"]').forEach(function (btn) {
        var a = btn.dataset.action;
        if (a === 'sc-reload') btn.addEventListener('click', function () { self.reload(); });
        if (a === 'sc-save') btn.addEventListener('click', function () { self.save(); });
        if (a === 'sc-delete') btn.addEventListener('click', function () { self.deleteSession(); });
        if (a === 'sc-clear') btn.addEventListener('click', function () { self.clearAll(); });
      });
      qs('#field-session-id').addEventListener('input', function (e) {
        self.store.form.session_id = e.target.value;
        self.renderButtons();
      });
      qs('#field-session-type').addEventListener('change', function (e) {
        self.store.form.session_type = e.target.value;
      });
      qs('#field-display-name').addEventListener('input', function (e) {
        self.store.form.display_name = e.target.value;
      });
    },
  };

  // ══════════════════════════════════════════════════════════════════════════
  // 访问控制模块
  // ══════════════════════════════════════════════════════════════════════════

  var MODE_OPTIONS = ['none', 'blacklist', 'whitelist'];
  var ACL_LABELS = {
    setu: 'Setu',
    fortune: '运势',
    user: '用户',
    group: '群组',
    blacklist: '黑名单',
    whitelist: '白名单',
  };

  var accessModule = {
    loaded: false,
    store: null,

    init: function () {
      if (this.loaded) return;
      this.loaded = true;

      this.store = createStore({
        loading: false,
        modes: {
          setu_user_access_control_mode: 'none',
          setu_group_access_control_mode: 'none',
          fortune_user_access_control_mode: 'none',
          fortune_group_access_control_mode: 'none',
        },
        entries: [],
        form: this.emptyForm(),
        formError: '',
        dialogOpen: false,
        lastFocus: null,
        filters: { search: '', feature: '', subject_type: '', list_type: '' },
      });

      this.bindEvents();
      this.reload();
    },

    emptyForm: function () {
      return { id: '', feature: 'setu', subject_type: 'user', list_type: 'blacklist', target_id: '', note: '' };
    },

    reload: function () {
      var self = this;
      var s = this.store;
      s.loading = true;
      self.renderButtons();
      apiGet('access-control').then(apiResult).then(function (result) {
        s.modes = Object.assign({}, s.modes, result.modes || {});
        s.entries = result.entries || [];
        self.renderAll();
      }).catch(function (err) {
        globalStore.showToast(err.message || '加载访问控制失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderButtons();
      });
    },

    saveModes: function () {
      var self = this;
      var s = this.store;
      s.loading = true;
      self.renderButtons();
      apiPost('access-control/modes', { modes: s.modes }).then(apiResult).then(function (result) {
        s.modes = Object.assign({}, s.modes, result.modes || {});
        self.renderModes();
        globalStore.showToast('模式已保存');
      }).catch(function (err) {
        globalStore.showToast(err.message || '保存模式失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderButtons();
      });
    },

    saveEntry: function () {
      var self = this;
      var s = this.store;
      var payload = Object.assign({}, s.form, { target_id: s.form.target_id.trim(), note: s.form.note.trim() });
      if (!payload.target_id) {
        self.setFormError('ID 不能为空，请填写用户 ID 或群组 ID。');
        qs('#field-target-id').focus();
        return;
      }
      s.formError = '';
      s.loading = true;
      self.renderButtons();
      apiPost('access-control/entries/upsert', payload).then(apiResult).then(function () {
        s.form = self.emptyForm();
        self.closeEntryModal(false, true);
        return self.reload();
      }).then(function () {
        globalStore.showToast('记录已保存');
      }).catch(function (err) {
        globalStore.showToast(err.message || '保存记录失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderButtons();
      });
    },

    editEntry: function (entry) {
      this.store.form = Object.assign({}, this.emptyForm(), entry);
      this.openEntryModal();
    },

    deleteEntry: function (id) {
      var self = this;
      var s = this.store;
      if (!id) return;
      s.loading = true;
      self.renderButtons();
      apiPost('access-control/entries/delete', { id: id }).then(apiResult).then(function () {
        if (s.form.id === id) {
          s.form = self.emptyForm();
          self.closeEntryModal(false, true);
        }
        return self.reload();
      }).then(function () {
        self.renderForm();
        globalStore.showToast('记录已删除');
      }).catch(function (err) {
        globalStore.showToast(err.message || '删除记录失败', 'error');
      }).finally(function () {
        s.loading = false;
        self.renderButtons();
      });
    },

    resetForm: function () {
      this.store.form = this.emptyForm();
      this.store.formError = '';
      this.renderForm();
      qs('#field-target-id').focus();
    },

    openCreateEntry: function () {
      this.store.form = this.emptyForm();
      this.openEntryModal();
    },

    openEntryModal: function () {
      var s = this.store;
      s.dialogOpen = true;
      s.formError = '';
      s.lastFocus = document.activeElement;
      this.renderForm();
      window.setTimeout(function () {
        var target = qs('#field-target-id');
        if (target) target.focus();
      }, 0);
    },

    closeEntryModal: function (resetForm, force) {
      var s = this.store;
      if (s.loading && !force) return;
      s.dialogOpen = false;
      s.formError = '';
      if (resetForm !== false) s.form = this.emptyForm();
      this.renderForm();
      if (s.lastFocus && typeof s.lastFocus.focus === 'function') {
        s.lastFocus.focus();
      }
      s.lastFocus = null;
    },

    setFormError: function (message) {
      this.store.formError = message || '';
      this.renderForm();
    },

    filteredEntries: function () {
      var s = this.store;
      var search = s.filters.search.trim().toLowerCase();
      return s.entries.filter(function (entry) {
        if (s.filters.feature && entry.feature !== s.filters.feature) return false;
        if (s.filters.subject_type && entry.subject_type !== s.filters.subject_type) return false;
        if (s.filters.list_type && entry.list_type !== s.filters.list_type) return false;
        if (!search) return true;
        return [entry.target_id, entry.note].join(' ').toLowerCase().includes(search);
      });
    },

    // ── 渲染 ──────────────────────────────────────────────────────────────

    renderAll: function () {
      this.renderModes();
      this.renderForm();
      this.renderEntries();
      this.renderButtons();
    },

    renderModes: function () {
      var fields = {
        '#mode-setu-user': 'setu_user_access_control_mode',
        '#mode-setu-group': 'setu_group_access_control_mode',
        '#mode-fortune-user': 'fortune_user_access_control_mode',
        '#mode-fortune-group': 'fortune_group_access_control_mode',
      };
      Object.keys(fields).forEach(function (selector) {
        var el = qs(selector);
        if (!el) return;
        if (!el.options.length) {
          MODE_OPTIONS.forEach(function (value) {
            var opt = document.createElement('option');
            opt.value = value;
            opt.textContent = value;
            el.appendChild(opt);
          });
        }
        el.value = this.store.modes[fields[selector]] || 'none';
      }.bind(this));
    },

    renderForm: function () {
      qs('#form-title').textContent = this.store.form.id ? '编辑记录' : '新增记录';
      qs('#field-feature').value = this.store.form.feature;
      qs('#field-subject-type').value = this.store.form.subject_type;
      qs('#field-list-type').value = this.store.form.list_type;
      qs('#field-target-id').value = this.store.form.target_id;
      qs('#field-note').value = this.store.form.note;
      this.renderModal();
      var error = qs('#entry-form-error');
      error.textContent = this.store.formError;
      error.hidden = !this.store.formError;
    },

    renderModal: function () {
      var modal = qs('#access-entry-modal');
      modal.hidden = !this.store.dialogOpen;
      modal.setAttribute('aria-hidden', this.store.dialogOpen ? 'false' : 'true');
      document.body.classList.toggle('modal-open', this.store.dialogOpen);
    },

    renderEntries: function () {
      var self = this;
      var body = qs('#entry-list');
      var rows = this.filteredEntries();
      body.innerHTML = '';
      qs('#empty-state').style.display = rows.length ? 'none' : '';
      rows.forEach(function (entry) {
        var tr = document.createElement('tr');
        tr.innerHTML =
          self.td('功能', self.pill(ACL_LABELS[entry.feature] || entry.feature)) +
          self.td('对象', escHtml(ACL_LABELS[entry.subject_type] || entry.subject_type)) +
          self.td('名单', escHtml(ACL_LABELS[entry.list_type] || entry.list_type)) +
          self.td('ID', '<strong>' + escHtml(entry.target_id) + '</strong>') +
          self.td('备注', escHtml(entry.note || '')) +
          '<td class="col-actions" data-label="操作"><div class="row-actions">' +
          '<button class="btn btn-text btn-action" data-edit="' + escHtml(entry.id) + '">编辑</button>' +
          '<button class="btn btn-text btn-action danger" data-delete="' + escHtml(entry.id) + '">删除</button>' +
          '</div></td>';
        body.appendChild(tr);
      });
      qsa('[data-edit]', body).forEach(function (btn) {
        btn.addEventListener('click', function () {
          var entry = self.store.entries.find(function (item) { return item.id === btn.dataset.edit; });
          if (entry) self.editEntry(entry);
        });
      });
      qsa('[data-delete]', body).forEach(function (btn) {
        btn.addEventListener('click', function () { self.deleteEntry(btn.dataset.delete); });
      });
    },

    td: function (label, html) {
      return '<td data-label="' + escHtml(label) + '">' + html + '</td>';
    },

    pill: function (text) {
      return '<span class="pill">' + escHtml(text) + '</span>';
    },

    renderButtons: function () {
      qsa('[data-action^="ac-"]').forEach(function (btn) { btn.disabled = !!this.store.loading; }.bind(this));
    },

    bindEvents: function () {
      var self = this;
      var s = this.store;

      qsa('[data-action^="ac-"]').forEach(function (btn) {
        var action = btn.dataset.action;
        if (action === 'ac-open-create') btn.addEventListener('click', function () { self.openCreateEntry(); });
        if (action === 'ac-close-entry-modal') btn.addEventListener('click', function () { self.closeEntryModal(); });
        if (action === 'ac-reload') btn.addEventListener('click', function () { self.reload(); });
        if (action === 'ac-save-modes') btn.addEventListener('click', function () { self.saveModes(); });
        if (action === 'ac-save-entry') btn.addEventListener('click', function () { self.saveEntry(); });
        if (action === 'ac-reset-form') btn.addEventListener('click', function () { self.resetForm(); });
      });

      var modeFields = {
        '#mode-setu-user': 'setu_user_access_control_mode',
        '#mode-setu-group': 'setu_group_access_control_mode',
        '#mode-fortune-user': 'fortune_user_access_control_mode',
        '#mode-fortune-group': 'fortune_group_access_control_mode',
      };
      Object.keys(modeFields).forEach(function (selector) {
        qs(selector).addEventListener('change', function (e) { s.modes[modeFields[selector]] = e.target.value; });
      });

      qs('#field-feature').addEventListener('change', function (e) { s.form.feature = e.target.value; });
      qs('#field-subject-type').addEventListener('change', function (e) { s.form.subject_type = e.target.value; });
      qs('#field-list-type').addEventListener('change', function (e) { s.form.list_type = e.target.value; });
      qs('#field-target-id').addEventListener('input', function (e) { s.form.target_id = e.target.value; });
      qs('#field-note').addEventListener('input', function (e) { s.form.note = e.target.value; });

      qs('[data-modal-close="access-entry"]').addEventListener('click', function () { self.closeEntryModal(); });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && s.dialogOpen) self.closeEntryModal();
      });

      qs('#filter-search').addEventListener('input', function (e) {
        s.filters.search = e.target.value;
        self.renderEntries();
      });
      qs('#filter-feature').addEventListener('change', function (e) {
        s.filters.feature = e.target.value;
        self.renderEntries();
      });
      qs('#filter-subject-type').addEventListener('change', function (e) {
        s.filters.subject_type = e.target.value;
        self.renderEntries();
      });
      qs('#filter-list-type').addEventListener('change', function (e) {
        s.filters.list_type = e.target.value;
        self.renderEntries();
      });
    },
  };

  // ══════════════════════════════════════════════════════════════════════════
  // 启动
  // ══════════════════════════════════════════════════════════════════════════

  function init() {
    // 绑定导航标签
    qsa('.nav-item').forEach(function (item) {
      item.addEventListener('click', function () { switchTab(item.dataset.tab); });
    });

    // 绑定汉堡按钮
    qs('#nav-hamburger').addEventListener('click', function () {
      qs('#nav-sidebar').classList.toggle('open');
      qs('#nav-overlay').classList.toggle('visible');
    });
    qs('#nav-overlay').addEventListener('click', closeMobileNav);

    // 初始化默认标签
    sessionModule.init();

    document.body.classList.add('ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
