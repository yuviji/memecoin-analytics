import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics for stress testing
const errorRate = new Rate('stress_error_rate');
const responseTime = new Trend('stress_response_time', true);
const throughput = new Counter('stress_throughput');

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_BASE = `${BASE_URL}/api/v1`;

// High-volume token addresses for stress testing
const STRESS_TOKENS = [
    'So11111111111111111111111111111111111111112', // SOL
    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263', // BONK
    'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm', // WIF
];

export let options = {
    scenarios: {
        // Breaking point test
        breaking_point: {
            executor: 'ramping-vus',
            startVUs: 50,
            stages: [
                { duration: '2m', target: 100 },   // Ramp up to 100 users
                { duration: '3m', target: 200 },   // Ramp up to 200 users  
                { duration: '2m', target: 500 },   // Ramp up to 500 users
                { duration: '5m', target: 500 },   // Stay at 500 users
                { duration: '2m', target: 1000 },  // Spike to 1000 users
                { duration: '3m', target: 1000 },  // Hold at 1000 users
                { duration: '2m', target: 0 },     // Ramp down
            ],
        },
        
        // Sustained high load
        sustained_load: {
            executor: 'constant-vus',
            vus: 200,
            duration: '10m',
            tags: { test_type: 'sustained' },
        },
        
        // Burst traffic simulation
        burst_traffic: {
            executor: 'ramping-arrival-rate',
            startRate: 10,
            timeUnit: '1s',
            stages: [
                { duration: '1m', target: 50 },    // 50 RPS
                { duration: '2m', target: 100 },   // 100 RPS
                { duration: '1m', target: 500 },   // 500 RPS burst
                { duration: '2m', target: 100 },   // Back to 100 RPS
                { duration: '1m', target: 0 },     // Cool down
            ],
        }
    },
    
    thresholds: {
        // Stress test thresholds - more lenient but still performant
        'http_req_duration': ['p(95)<2000', 'p(99)<5000'], 
        'http_req_failed': ['rate<0.10'], // Allow 10% failure under stress
        'stress_error_rate': ['rate<0.15'], // Custom metric threshold
        'http_req_duration{test_type:sustained}': ['p(95)<1000'], // Sustained load
    }
};

export function setup() {
    console.log('🔥 STRESS TEST: Finding Breaking Point');
    console.log(`🎯 Target: ${BASE_URL}`);
    console.log('📊 Testing scenarios: Breaking Point, Sustained Load, Burst Traffic');
    
    // Warm up the system
    http.get(`${BASE_URL}/health`);
    return { tokens: STRESS_TOKENS };
}

export default function(data) {
    const token = data.tokens[Math.floor(Math.random() * data.tokens.length)];
    const scenario = __ENV.SCENARIO || 'mixed';
    
    // Mix of different endpoint types to simulate realistic stress
    const actions = [
        () => stressHealthCheck(),
        () => stressTokenMetrics(token),
        () => stressAnalytics(token),
        () => stressPriceCheck(token),
        () => stressConcurrentRequests(token)
    ];
    
    // Execute random action based on realistic distribution
    const actionWeights = [0.1, 0.3, 0.4, 0.15, 0.05]; // Health, Metrics, Analytics, Price, Concurrent
    const random = Math.random();
    let cumulative = 0;
    
    for (let i = 0; i < actions.length; i++) {
        cumulative += actionWeights[i];
        if (random <= cumulative) {
            actions[i]();
            break;
        }
    }
    
    // Minimal sleep under stress - real users don't wait much during volatility
    sleep(Math.random() * 0.5 + 0.1); // 100ms to 600ms
}

function stressHealthCheck() {
    const response = http.get(`${BASE_URL}/health`, {
        timeout: '5s',
    });
    
    throughput.add(1);
    
    const success = check(response, {
        'Health check survives stress': (r) => r.status === 200,
        'Health check fast under stress': (r) => r.timings.duration < 1000,
    });
    
    recordStressMetrics(response, success);
}

function stressTokenMetrics(token) {
    const response = http.get(`${API_BASE}/tokens/${token}/metrics`, {
        timeout: '10s',
    });
    
    throughput.add(1);
    
    const success = check(response, {
        'Metrics survive stress': (r) => r.status === 200 || r.status === 404,
        'Metrics reasonable under stress': (r) => r.timings.duration < 3000,
    });
    
    recordStressMetrics(response, success);
}

function stressAnalytics(token) {
    const endpoints = [
        `/tokens/${token}/concentration`,
        `/tokens/${token}/velocity`,
        `/tokens/${token}/paperhand`
    ];
    
    const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
    const response = http.get(`${API_BASE}${endpoint}`, {
        timeout: '15s',
    });
    
    throughput.add(1);
    
    const success = check(response, {
        'Analytics survive stress': (r) => r.status === 200 || r.status === 404,
        'Analytics complete under stress': (r) => r.timings.duration < 5000,
    });
    
    recordStressMetrics(response, success);
}

function stressPriceCheck(token) {
    const response = http.get(`${API_BASE}/tokens/${token}/price`, {
        timeout: '8s',
    });
    
    throughput.add(1);
    
    const success = check(response, {
        'Price check survives stress': (r) => r.status === 200 || r.status === 404,
        'Price check fast under stress': (r) => r.timings.duration < 2000,
    });
    
    recordStressMetrics(response, success);
}

function stressConcurrentRequests(token) {
    // Simulate burst of concurrent requests from same user
    const requests = [];
    for (let i = 0; i < 3; i++) {
        requests.push(['GET', `${API_BASE}/tokens/${token}/price`, null, { timeout: '10s' }]);
    }
    
    const responses = http.batch(requests);
    throughput.add(3);
    
    const success = check(responses, {
        'Concurrent requests survive': (resps) => resps.every(r => r.status === 200 || r.status === 404),
        'Concurrent batch completes': (resps) => resps.length === 3,
    });
    
    // Record metrics for all responses
    responses.forEach(response => recordStressMetrics(response, success));
}

function recordStressMetrics(response, success) {
    responseTime.add(response.timings.duration);
    
    if (!success || response.status >= 400) {
        errorRate.add(1);
    } else {
        errorRate.add(0);
    }
}

export function teardown(data) {
    console.log('🔥 Stress test completed!');
    console.log('📊 Check results to see if system survived the stress');
}

export function handleSummary(data) {
    const metrics = data.metrics;
    
    // Determine if system passed stress test
    const passedErrorRate = metrics.http_req_failed.values.rate < 0.10;
    const passedResponseTime = metrics.http_req_duration.values['p(95)'] < 2000;
    const passedThroughput = metrics.http_reqs.values.rate > 50; // Minimum 50 RPS
    
    const overallPassed = passedErrorRate && passedResponseTime && passedThroughput;
    
    const summary = `
🔥 STRESS TEST RESULTS - TROJAN TRADING ANALYTICS
===============================================

🎯 Stress Test Criteria:
- Error Rate: < 10% under stress
- P95 Response Time: < 2000ms under stress  
- Minimum Throughput: > 50 RPS
- System Stability: No crashes/timeouts

📊 Performance Under Stress:
- Total Requests: ${metrics.http_reqs.values.count}
- Request Rate: ${metrics.http_reqs.values.rate.toFixed(2)} RPS
- Failed Requests: ${(metrics.http_req_failed.values.rate * 100).toFixed(2)}%
- Average Response: ${metrics.http_req_duration.values.avg.toFixed(2)}ms
- P95 Response: ${metrics.http_req_duration.values['p(95)'].toFixed(2)}ms
- P99 Response: ${metrics.http_req_duration.values['p(99)'].toFixed(2)}ms
- Max Response: ${metrics.http_req_duration.values.max.toFixed(2)}ms

🚦 Stress Test Results:
${passedErrorRate ? '✅' : '❌'} Error Rate (${(metrics.http_req_failed.values.rate * 100).toFixed(2)}%)
${passedResponseTime ? '✅' : '❌'} Response Time (${metrics.http_req_duration.values['p(95)'].toFixed(2)}ms)
${passedThroughput ? '✅' : '❌'} Throughput (${metrics.http_reqs.values.rate.toFixed(2)} RPS)

🎯 Overall Result: ${overallPassed ? '✅ PASSED' : '❌ FAILED'}

${overallPassed ? 
    '🚀 System handles stress well! Ready for volatile memecoin markets!' :
    '⚠️  System needs optimization for high-stress scenarios.'}
`;

    return {
        'stress-results.json': JSON.stringify(data, null, 2),
        stdout: summary,
    };
} 