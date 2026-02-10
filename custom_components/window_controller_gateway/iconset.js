const windowControllerIcons = {
  "window-controller-gateway": {
    path: "M3 3h18v18H3V3zm2 2v14h14V5H5zm4 2h6v2H9V7zm0 4h6v2H9v-2zm0 4h6v2H9v-2z",
    keywords: ["window", "controller", "gateway"]
  },
  "window-opener": {
    path: "M3 3h18v18H3V3zm2 2v14h14V5H5zm4 2h6v6H9V7zm2 2v2h2v-2h-2z",
    keywords: ["window", "opener"]
  }
};

window.customIcons = window.customIcons || {};
window.customIconsets = window.customIconsets || {};

window.customIcons["window-controller-gateway"] = {
  getIcon: async (iconName) => ({
    path: windowControllerIcons[iconName]?.path
  }),
  getIconList: async () =>
    Object.entries(windowControllerIcons).map(([icon, content]) => ({
      name: icon,
      keywords: content.keywords
    }))
};
