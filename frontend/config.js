// API 配置
// 开发环境使用本地地址，生产环境修改为实际后端地址
const CONFIG = {
    // 后端 API 地址（生产环境请修改为实际部署地址）
    API_BASE: 'http://localhost:8000',
    
    // 示例生产环境配置:
    // API_BASE: 'https://api.yunitechhk.com',
};

// 导出配置
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}
