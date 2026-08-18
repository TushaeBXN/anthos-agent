const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('anthosDesktop', {
  getConnection: profile => ipcRenderer.invoke('anthos:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('anthos:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('anthos:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('anthos:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('anthos:window:openSession', sessionId, opts),
  openNewSessionWindow: () => ipcRenderer.invoke('anthos:window:openNewSession'),
  getBootProgress: () => ipcRenderer.invoke('anthos:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('anthos:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('anthos:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('anthos:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('anthos:connection-config:test', payload),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('anthos:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('anthos:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('anthos:connection-config:oauth-logout', remoteUrl),
  profile: {
    get: () => ipcRenderer.invoke('anthos:profile:get'),
    set: name => ipcRenderer.invoke('anthos:profile:set', name)
  },
  api: request => ipcRenderer.invoke('anthos:api', request),
  notify: payload => ipcRenderer.invoke('anthos:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('anthos:requestMicrophoneAccess'),
  readFileDataUrl: filePath => ipcRenderer.invoke('anthos:readFileDataUrl', filePath),
  readFileText: filePath => ipcRenderer.invoke('anthos:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('anthos:selectPaths', options),
  writeClipboard: text => ipcRenderer.invoke('anthos:writeClipboard', text),
  saveImageFromUrl: url => ipcRenderer.invoke('anthos:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('anthos:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('anthos:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('anthos:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('anthos:watchPreviewFile', url),
  stopPreviewFileWatch: id => ipcRenderer.invoke('anthos:stopPreviewFileWatch', id),
  setTitleBarTheme: payload => ipcRenderer.send('anthos:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('anthos:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('anthos:translucency', payload),
  setPreviewShortcutActive: active => ipcRenderer.send('anthos:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('anthos:openExternal', url),
  fetchLinkTitle: url => ipcRenderer.invoke('anthos:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('anthos:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('anthos:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('anthos:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('anthos:setting:defaultProjectDir:pick')
  },
  revealLogs: () => ipcRenderer.invoke('anthos:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('anthos:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('anthos:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('anthos:fs:gitRoot', startPath),
  worktrees: cwds => ipcRenderer.invoke('anthos:fs:worktrees', cwds),
  terminal: {
    dispose: id => ipcRenderer.invoke('anthos:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('anthos:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('anthos:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('anthos:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `anthos:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `anthos:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('anthos:close-preview-requested', listener)
    return () => ipcRenderer.removeListener('anthos:close-preview-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('anthos:open-updates', listener)
    return () => ipcRenderer.removeListener('anthos:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('anthos:deep-link', listener)
    return () => ipcRenderer.removeListener('anthos:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('anthos:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('anthos:window-state-changed', listener)
    return () => ipcRenderer.removeListener('anthos:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('anthos:focus-session', listener)
    return () => ipcRenderer.removeListener('anthos:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('anthos:notification-action', listener)
    return () => ipcRenderer.removeListener('anthos:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('anthos:preview-file-changed', listener)
    return () => ipcRenderer.removeListener('anthos:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('anthos:backend-exit', listener)
    return () => ipcRenderer.removeListener('anthos:backend-exit', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('anthos:power-resume', listener)
    return () => ipcRenderer.removeListener('anthos:power-resume', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('anthos:boot-progress', listener)
    return () => ipcRenderer.removeListener('anthos:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.cjs (apps/desktop/electron/bootstrap-runner.cjs).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('anthos:bootstrap:get'),
  resetBootstrap: () => ipcRenderer.invoke('anthos:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('anthos:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('anthos:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('anthos:bootstrap:event', listener)
    return () => ipcRenderer.removeListener('anthos:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('anthos:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('anthos:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('anthos:uninstall:summary'),
    run: mode => ipcRenderer.invoke('anthos:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('anthos:updates:check'),
    apply: opts => ipcRenderer.invoke('anthos:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('anthos:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('anthos:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('anthos:updates:progress', listener)
      return () => ipcRenderer.removeListener('anthos:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('anthos:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('anthos:vscode-theme:search', query)
  }
})
