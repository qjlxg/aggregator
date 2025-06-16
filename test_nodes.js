const fs = require('fs/promises'); // 用于异步文件操作
const yaml = require('js-yaml');   // 用于解析 YAML 文件
const path = require('path');     // 用于路径操作

// 辅助函数：测试延迟
async function testLatency(url, timeout = 5000) {
    const start = Date.now();
    try {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), timeout);
        const response = await fetch(url, { method: 'HEAD', redirect: 'follow', signal: controller.signal });
        clearTimeout(id);
        if (response.ok) {
            return Date.now() - start;
        }
        return -1; // 失败
    } catch (error) {
        if (error.name === 'AbortError') {
            return `超时 (${timeout}ms)`;
        }
        return `错误: ${error.message.substring(0, 50)}...`; // 截断错误信息
    }
}

// 辅助函数：测试下载速度
async function testDownloadSpeed(url, sizeBytes = 1000000, timeout = 10000) { // 默认1MB，10秒超时
    const start = Date.now();
    try {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), timeout);

        const response = await fetch(url, { method: 'GET', signal: controller.signal });
        clearTimeout(id);

        if (!response.ok) {
            return `下载失败 (状态码: ${response.status})`;
        }

        const reader = response.body.getReader();
        let downloadedBytes = 0;
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            downloadedBytes += value.length;
            // 如果下载量超过预期，可以提前结束
            if (downloadedBytes >= sizeBytes) break;
        }

        const duration = (Date.now() - start) / 1000; // 秒
        if (duration === 0) return "计算错误 (持续时间为0)";
        const speedMbps = (downloadedBytes * 8 / (1024 * 1024)) / duration; // Mbps
        return `${speedMbps.toFixed(2)} Mbps (${(downloadedBytes / (1024 * 1024)).toFixed(2)} MB)`;
    } catch (error) {
        if (error.name === 'AbortError') {
            return `下载超时 (${timeout}ms)`;
        }
        return `下载测试异常: ${error.message.substring(0, 50)}...`;
    }
}

// 主测试函数
async function runNodeTests() {
    const inputFilePath = path.join(__dirname, 'data', '520.yaml');
    const outputFilePath = path.join(__dirname, 'data', '521.yaml');

    let nodesConfig;
    try {
        const fileContent = await fs.readFile(inputFilePath, 'utf8');
        nodesConfig = yaml.load(fileContent);
        if (!nodesConfig || !Array.isArray(nodesConfig.nodes)) {
            throw new Error('520.yaml 文件格式不正确，缺少 "nodes" 数组。');
        }
    } catch (error) {
        console.error(`读取或解析 520.yaml 失败: ${error.message}`);
        return {
            timestamp: new Date().toISOString(),
            error: `读取或解析 520.yaml 失败: ${error.message}`
        };
    }

    console.log(`开始测试 ${nodesConfig.nodes.length} 个节点...`);
    const testResults = [];

    for (const node of nodesConfig.nodes) {
        console.log(`正在测试节点: ${node.name}`);
        const result = {
            name: node.name,
            url: node.url,
            latency_ms: await testLatency(node.url),
            download_speed: "未测试"
        };

        // 如果节点URL看起来像一个下载链接，则进行下载测速
        if (node.url.includes('speed.cloudflare.com/__down') || node.url.includes('github.com/releases/download')) {
             // 从 URL 中提取下载字节数，如果没有则默认 1MB
            const bytesMatch = node.url.match(/bytes=(\d+)/);
            const downloadSizeBytes = bytesMatch ? parseInt(bytesMatch[1], 10) : 1000000;
            result.download_speed = await testDownloadSpeed(node.url, downloadSizeBytes);
        }
        
        testResults.push(result);
    }

    const finalReport = {
        timestamp: new Date().toISOString(),
        tested_nodes_count: testResults.length,
        results: testResults
    };

    try {
        // 将结果写入 521.yaml
        await fs.writeFile(outputFilePath, yaml.dump(finalReport), 'utf8');
        console.log(`测试结果已成功写入 ${outputFilePath}`);
    } catch (error) {
        console.error(`写入 521.yaml 失败: ${error.message}`);
    }

    return finalReport;
}

// 当脚本直接执行时运行测试
if (require.main === module) {
    runNodeTests().then(results => {
        console.log("\n--- 测试完成 ---");
        // console.log(JSON.stringify(results, null, 2)); // 可以打印最终结果到控制台
    }).catch(error => {
        console.error("运行测试时发生未捕获错误:", error);
        process.exit(1); // 退出并返回非零状态码表示失败
    });
}
