(function () {
  const bridge = window.AstrBotPluginPage || null;
  let toastTimer = null;

  function emptyForm() {
    return {
      session_id: '',
      session_type: 'group',
      display_name: '',
      overrides: {},
    };
  }

  function apiResult(result) {
    if (result && result.success === false) {
      throw new Error(result.error || '请求失败');
    }
    return result || {};
  }

  const store = {
    loading: false,
    keys: [],
    sessions: [],
    globalValues: {},
    form: emptyForm(),
    toast: {show: false, type: 'success', message: ''},

    async reload() {
      this.loading = true;
      try {
        if (!bridge) throw new Error('AstrBotPluginPage bridge not available');
        await bridge.ready();
        const result = apiResult(await bridge.apiGet('session-config'));
        this.keys = result.keys || [];
        this.sessions = result.sessions || [];
        this.globalValues = result.global || {};
        if (this.form.session_id) {
          const selected = this.sessions.find((item) => item.session_id === this.form.session_id);
          if (selected) this.selectSession(selected);
        }
      } catch (err) {
        this.showToast(err.message || '加载失败', 'error');
      } finally {
        this.loading = false;
      }
    },

    newSession() {
      this.form = emptyForm();
    },

    selectSession(session) {
      this.form = {
        session_id: session.session_id || '',
        session_type: session.session_type || 'group',
        display_name: session.display_name || '',
        overrides: {...(session.overrides || {})},
      };
    },

    hasOverride(key) {
      return Object.prototype.hasOwnProperty.call(this.form.overrides, key);
    },

    toggleOverride(key, enabled) {
      if (enabled) {
        this.form.overrides[key] = this.effectiveValue(key);
      } else {
        delete this.form.overrides[key];
      }
    },

    effectiveValue(key) {
      return this.hasOverride(key) ? this.form.overrides[key] : this.globalValues[key];
    },

    displayValue(value) {
      if (value === true) return '启用';
      if (value === false) return '禁用';
      if (value === '' || value === undefined || value === null) return '空';
      return String(value);
    },

    async save() {
      if (!this.form.session_id.trim()) {
        this.showToast('session_id 不能为空', 'error');
        return;
      }
      this.loading = true;
      try {
        const result = apiResult(await bridge.apiPost('session-config/upsert', this.form));
        this.selectSession(result.data || this.form);
        await this.reload();
        this.showToast('已保存');
      } catch (err) {
        this.showToast(err.message || '保存失败', 'error');
      } finally {
        this.loading = false;
      }
    },

    async clearAll() {
      if (!this.form.session_id) return;
      this.loading = true;
      try {
        const result = apiResult(await bridge.apiPost('session-config/clear', this.form));
        this.selectSession(result.data || this.form);
        await this.reload();
        this.showToast('已清空覆盖');
      } catch (err) {
        this.showToast(err.message || '清空失败', 'error');
      } finally {
        this.loading = false;
      }
    },

    async deleteSession() {
      if (!this.form.session_id) return;
      this.loading = true;
      try {
        apiResult(await bridge.apiPost('session-config/delete', {session_id: this.form.session_id}));
        this.form = emptyForm();
        await this.reload();
        this.showToast('已删除');
      } catch (err) {
        this.showToast(err.message || '删除失败', 'error');
      } finally {
        this.loading = false;
      }
    },

    showToast(message, type = 'success') {
      if (toastTimer) window.clearTimeout(toastTimer);
      this.toast = {show: true, type, message};
      toastTimer = window.setTimeout(() => {
        this.toast.show = false;
      }, 2600);
    },
  };

  window.sessionConfigStore = store;
  PetiteVue.createApp(store).mount('#app');
  document.body.classList.add('ready');
  store.reload();
})();
