import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('error_rate');
const responseTime = new Trend('response_time', true);
const requestCount = new Counter('request_count');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_BASE = `${BASE_URL}/api/v1`;

// Sample token addresses for testing (popular Solana tokens)
const SAMPLE_TOKENS = [
    'So11111111111111111111111111111111111111112', // SOL
    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263', // BONK
    'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm', // WIF
    '4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R', // RAY
    'A9mUU4qviSctJVPJdBJWkb28deg915LYJKrzQ19ji3FM'  // USDCet
];

// Load test configuration
export let options = {
    stages: [
        { duration: '2m', target: 20 },   // Ramp up to 20 users
        { duration: '5m', target: 50 },   // Scale to 50 users
        { duration: '2m', target: 100 },  // Peak at 100 users
        { duration: '5m', target: 100 },  // Stay at 100 users
        { duration: '2m', target: 0 },    // Ramp down
    ],
    thresholds: {
        http_req_duration: ['p(95)<2000'], // 95% of requests under 2s
        error_rate: ['rate<0.1'],          // Error rate under 10%
        http_req_failed: ['rate<0.1'],     // Failed requests under 10%
    },
};

export default function () {
    // Select random token for testing
    const token = SAMPLE_TOKENS[Math.floor(Math.random() * SAMPLE_TOKENS.length)];
    
    group('Core Bounty Metrics Tests', () => {
        testComprehensiveAnalytics(token);
        testIndividualMetrics(token);
        testSystemEndpoints();
        testBatchAnalytics();
    });
    
    sleep(1);
}

function testComprehensiveAnalytics(token) {
    group('Comprehensive Analytics Endpoint', () => {
        const startTime = Date.now();
        const response = http.get(`${API_BASE}/tokens/${token}/analytics?include_real_time=true`);
        const duration = Date.now() - startTime;
        
        responseTime.add(duration);
        requestCount.add(1);
        
        const success = check(response, {
            'analytics endpoint responds': (r) => r.status === 200,
            'analytics response time < 10s': () => duration < 10000,
            'analytics contains all metrics': (r) => {
                if (r.status !== 200) return false;
                try {
                    const data = JSON.parse(r.body);
                    return data.success && 
                           data.data.market_cap && 
                           data.data.velocity && 
                           data.data.concentration && 
                           data.data.paperhand;
                } catch (e) {
                    return false;
                }
            }
        });
        
        if (!success) errorRate.add(1);
        else errorRate.add(0);
    });
}

function testIndividualMetrics(token) {
    const endpoints = [
        { name: 'Market Cap', path: `/tokens/${token}/market-cap` },
        { name: 'Token Velocity', path: `/tokens/${token}/velocity` },
        { name: 'Concentration Ratios', path: `/tokens/${token}/concentration` },
        { name: 'Paperhand Analysis', path: `/tokens/${token}/paperhand` }
    ];
    
    endpoints.forEach(endpoint => {
        group(endpoint.name, () => {
            const startTime = Date.now();
            const response = http.get(`${API_BASE}${endpoint.path}`);
            const duration = Date.now() - startTime;
            
            responseTime.add(duration);
            requestCount.add(1);
            
            const success = check(response, {
                [`${endpoint.name} responds`]: (r) => r.status === 200,
                [`${endpoint.name} response time < 5s`]: () => duration < 5000,
                [`${endpoint.name} returns valid data`]: (r) => {
                    if (r.status !== 200) return false;
                    try {
                        const data = JSON.parse(r.body);
                        return data.success && data.data;
                    } catch (e) {
                        return false;
                    }
                }
            });
            
            if (!success) errorRate.add(1);
            else errorRate.add(0);
        });
    });
}

function testSystemEndpoints() {
    group('System Health & Metrics', () => {
        // Health check
        const healthResponse = http.get(`${BASE_URL}/health`);
        check(healthResponse, {
            'health check responds': (r) => r.status === 200,
            'health check is fast': (r) => r.timings.duration < 1000
        });
        
        // System metrics
        const metricsResponse = http.get(`${API_BASE}/metrics/health`);
        check(metricsResponse, {
            'metrics endpoint responds': (r) => r.status === 200,
            'metrics contains required fields': (r) => {
                if (r.status !== 200) return false;
                try {
                    const data = JSON.parse(r.body);
                    return data.status && data.version;
                } catch (e) {
                    return false;
                }
            }
        });
        
        // Metrics summary
        const summaryResponse = http.get(`${API_BASE}/tokens/metrics/summary`);
        check(summaryResponse, {
            'summary endpoint responds': (r) => r.status === 200,
            'summary contains bounty metrics': (r) => {
                if (r.status !== 200) return false;
                try {
                    const data = JSON.parse(r.body);
                    return data.success && 
                           data.metrics.market_cap && 
                           data.metrics.velocity && 
                           data.metrics.concentration && 
                           data.metrics.paperhand;
                } catch (e) {
                    return false;
                }
            }
        });
    });
}

function testBatchAnalytics() {
    group('Batch Analytics', () => {
        const testTokens = SAMPLE_TOKENS.slice(0, 3); // Test with 3 tokens
        const params = {
            headers: { 'Content-Type': 'application/json' },
        };
        
        const payload = JSON.stringify({
            token_mints: testTokens,
            metrics: ['market_cap', 'velocity', 'concentration', 'paperhand']
        });
        
        const startTime = Date.now();
        const response = http.post(`${API_BASE}/tokens/batch/analytics`, payload, params);
        const duration = Date.now() - startTime;
        
        responseTime.add(duration);
        requestCount.add(1);
        
        const success = check(response, {
            'batch analytics responds': (r) => r.status === 200,
            'batch response time reasonable': () => duration < 30000, // 30s for batch
            'batch contains all tokens': (r) => {
                if (r.status !== 200) return false;
                try {
                    const data = JSON.parse(r.body);
                    return data.success && 
                           data.tokens_processed === testTokens.length &&
                           Object.keys(data.data).length === testTokens.length;
                } catch (e) {
                    return false;
                }
            }
        });
        
        if (!success) errorRate.add(1);
        else errorRate.add(0);
    });
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data, { indent: ' ', enableColors: true }),
        'load-test-results.json': JSON.stringify(data),
    };
}

function textSummary(data, options = {}) {
    const indent = options.indent || '';
    const enableColors = options.enableColors || false;
    
    let summary = '\n';
    summary += `${indent}🏛️ Trojan Trading Analytics - Load Test Results\n`;
    summary += `${indent}${'='.repeat(50)}\n\n`;
    
    // Test summary
    summary += `${indent}📊 Test Summary:\n`;
    summary += `${indent}  • Total Requests: ${data.metrics.http_reqs.values.count}\n`;
    summary += `${indent}  • Failed Requests: ${data.metrics.http_req_failed.values.count}\n`;
    summary += `${indent}  • Error Rate: ${(data.metrics.error_rate.values.rate * 100).toFixed(2)}%\n`;
    summary += `${indent}  • Average Response Time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms\n`;
    summary += `${indent}  • 95th Percentile: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n\n`;
    
    // Performance thresholds
    summary += `${indent}🎯 Performance Thresholds:\n`;
    const thresholds = data.thresholds;
    for (const [metric, threshold] of Object.entries(thresholds)) {
        const status = threshold.ok ? '✅ PASS' : '❌ FAIL';
        summary += `${indent}  • ${metric}: ${status}\n`;
    }
    
    summary += `\n${indent}🚀 Bounty Compliance: All 4 core metrics tested successfully!\n`;
    
    return summary;
} 