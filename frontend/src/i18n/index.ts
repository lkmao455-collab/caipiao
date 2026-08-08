// 国际化翻译

export type Locale = "zh-CN" | "en-US";

export interface Translation {
  // 通用
  common: {
    appTitle: string;
    loading: string;
    error: string;
    success: string;
    cancel: string;
    confirm: string;
    save: string;
    delete: string;
    edit: string;
    add: string;
    search: string;
    reset: string;
    export: string;
    import: string;
  };
  // 导航
  nav: {
    generate: string;
    stats: string;
    backtest: string;
    filters: string;
    compare: string;
    favorites: string;
    recommend: string;
    dashboard: string;
    multiPeriod: string;
    tasks: string;
    admin: string;
  };
  // 生成
  generate: {
    title: string;
    selectProfile: string;
    selectStrategy: string;
    count: string;
    button: string;
    result: string;
    copyAll: string;
    clear: string;
  };
  // 统计
  stats: {
    title: string;
    frequency: string;
    hotNumbers: string;
    coldNumbers: string;
    missingValues: string;
    oddEven: string;
    bigSmall: string;
    sumRange: string;
    pullLatest: string;
    pullAll: string;
    exportCSV: string;
  };
  // 回测
  backtest: {
    title: string;
    rounds: string;
    ticketsPerRound: string;
    start: string;
    history: string;
    summary: string;
    hitRate: string;
    profit: string;
  };
  // 过滤
  filters: {
    title: string;
    rules: string;
    addRule: string;
    apply: string;
    clear: string;
  };
  // 对比
  compare: {
    title: string;
    selectStrategies: string;
    analyze: string;
    frequency: string;
    overlap: string;
  };
  // 登录
  auth: {
    login: string;
    register: string;
    username: string;
    password: string;
    email: string;
    loginButton: string;
    registerButton: string;
    hasAccount: string;
    noAccount: string;
    logout: string;
  };
  // 管理
  admin: {
    title: string;
    users: string;
    roles: string;
    settings: string;
  };
  // 设置
  settings: {
    title: string;
    language: string;
    theme: string;
    darkMode: string;
    lightMode: string;
  };
  // 客服
  chatbot: {
    title: string;
    placeholder: string;
    send: string;
    welcome: string;
  };
  // 社区
  community: {
    title: string;
    share: string;
    comments: string;
    likes: string;
    leaderboard: string;
  };
}

export const zhCN: Translation = {
  common: {
    appTitle: "彩票号码生成器",
    loading: "加载中...",
    error: "错误",
    success: "成功",
    cancel: "取消",
    confirm: "确认",
    save: "保存",
    delete: "删除",
    edit: "编辑",
    add: "添加",
    search: "搜索",
    reset: "重置",
    export: "导出",
    import: "导入",
  },
  nav: {
    generate: "生成",
    stats: "统计",
    backtest: "回测",
    filters: "过滤",
    compare: "对比",
    favorites: "收藏",
    recommend: "推荐",
    dashboard: "大屏",
    multiPeriod: "多期",
    tasks: "任务",
    admin: "管理",
  },
  generate: {
    title: "号码生成",
    selectProfile: "选择彩种",
    selectStrategy: "选择策略",
    count: "生成数量",
    button: "生成号码",
    result: "生成结果",
    copyAll: "复制全部",
    clear: "清空",
  },
  stats: {
    title: "数据统计",
    frequency: "号码频率",
    hotNumbers: "热号",
    coldNumbers: "冷号",
    missingValues: "遗漏值",
    oddEven: "奇偶比",
    bigSmall: "大小比",
    sumRange: "和值分布",
    pullLatest: "拉取最新",
    pullAll: "拉取全量",
    exportCSV: "导出 CSV",
  },
  backtest: {
    title: "策略回测",
    rounds: "回测期数",
    ticketsPerRound: "每期注数",
    start: "开始回测",
    history: "回测历史",
    summary: "回测总结",
    hitRate: "命中率",
    profit: "盈亏",
  },
  filters: {
    title: "后过滤规则",
    rules: "规则列表",
    addRule: "添加规则",
    apply: "应用过滤",
    clear: "清空规则",
  },
  compare: {
    title: "策略对比",
    selectStrategies: "选择策略",
    analyze: "开始分析",
    frequency: "频率对比",
    overlap: "重叠分析",
  },
  auth: {
    login: "登录",
    register: "注册",
    username: "用户名",
    password: "密码",
    email: "邮箱",
    loginButton: "登录",
    registerButton: "注册",
    hasAccount: "已有账号？",
    noAccount: "没有账号？",
    logout: "退出登录",
  },
  admin: {
    title: "系统管理",
    users: "用户管理",
    roles: "角色管理",
    settings: "系统设置",
  },
  settings: {
    title: "设置",
    language: "语言",
    theme: "主题",
    darkMode: "深色模式",
    lightMode: "浅色模式",
  },
  chatbot: {
    title: "智能客服",
    placeholder: "输入您的问题...",
    send: "发送",
    welcome: "您好！我是智能客服助手，可以帮您解答关于彩票号码生成器的使用问题。",
  },
  community: {
    title: "社区",
    share: "分享",
    comments: "评论",
    likes: "点赞",
    leaderboard: "排行榜",
  },
};

export const enUS: Translation = {
  common: {
    appTitle: "Lottery Number Generator",
    loading: "Loading...",
    error: "Error",
    success: "Success",
    cancel: "Cancel",
    confirm: "Confirm",
    save: "Save",
    delete: "Delete",
    edit: "Edit",
    add: "Add",
    search: "Search",
    reset: "Reset",
    export: "Export",
    import: "Import",
  },
  nav: {
    generate: "Generate",
    stats: "Stats",
    backtest: "Backtest",
    filters: "Filters",
    compare: "Compare",
    favorites: "Favorites",
    recommend: "Recommend",
    dashboard: "Dashboard",
    multiPeriod: "Multi-Period",
    tasks: "Tasks",
    admin: "Admin",
  },
  generate: {
    title: "Number Generation",
    selectProfile: "Select Lottery",
    selectStrategy: "Select Strategy",
    count: "Count",
    button: "Generate Numbers",
    result: "Results",
    copyAll: "Copy All",
    clear: "Clear",
  },
  stats: {
    title: "Data Statistics",
    frequency: "Number Frequency",
    hotNumbers: "Hot Numbers",
    coldNumbers: "Cold Numbers",
    missingValues: "Missing Values",
    oddEven: "Odd/Even Ratio",
    bigSmall: "Big/Small Ratio",
    sumRange: "Sum Distribution",
    pullLatest: "Pull Latest",
    pullAll: "Pull All",
    exportCSV: "Export CSV",
  },
  backtest: {
    title: "Strategy Backtest",
    rounds: "Rounds",
    ticketsPerRound: "Tickets per Round",
    start: "Start Backtest",
    history: "Backtest History",
    summary: "Summary",
    hitRate: "Hit Rate",
    profit: "Profit",
  },
  filters: {
    title: "Post Filters",
    rules: "Rules",
    addRule: "Add Rule",
    apply: "Apply Filters",
    clear: "Clear Rules",
  },
  compare: {
    title: "Strategy Comparison",
    selectStrategies: "Select Strategies",
    analyze: "Analyze",
    frequency: "Frequency Comparison",
    overlap: "Overlap Analysis",
  },
  auth: {
    login: "Login",
    register: "Register",
    username: "Username",
    password: "Password",
    email: "Email",
    loginButton: "Login",
    registerButton: "Register",
    hasAccount: "Already have an account?",
    noAccount: "Don't have an account?",
    logout: "Logout",
  },
  admin: {
    title: "System Admin",
    users: "User Management",
    roles: "Role Management",
    settings: "System Settings",
  },
  settings: {
    title: "Settings",
    language: "Language",
    theme: "Theme",
    darkMode: "Dark Mode",
    lightMode: "Light Mode",
  },
  chatbot: {
    title: "AI Assistant",
    placeholder: "Type your question...",
    send: "Send",
    welcome: "Hello! I'm your AI assistant. How can I help you with the lottery number generator?",
  },
  community: {
    title: "Community",
    share: "Share",
    comments: "Comments",
    likes: "Likes",
    leaderboard: "Leaderboard",
  },
};

// 翻译函数
const translations: Record<Locale, Translation> = {
  "zh-CN": zhCN,
  "en-US": enUS,
};

let currentLocale: Locale = "zh-CN";
try {
  const saved = localStorage.getItem("locale");
  if (saved && (saved === "zh-CN" || saved === "en-US")) {
    currentLocale = saved;
  }
} catch {
  // 忽略 localStorage 不可用的情况
}

export function setLocale(locale: Locale) {
  currentLocale = locale;
  try {
    localStorage.setItem("locale", locale);
  } catch {
    // 忽略 localStorage 不可用的情况
  }
}

export function getLocale(): Locale {
  return currentLocale;
}

export function t(path: string): string {
  const keys = path.split(".");
  let result: any = translations[currentLocale];

  for (const key of keys) {
    if (result && typeof result === "object" && key in result) {
      result = result[key];
    } else {
      return path;
    }
  }

  return typeof result === "string" ? result : path;
}
