# Helius API Comprehensive Test Suite

This test suite thoroughly tests **every single API endpoint** used in the Helius Client implementation with real data and live APIs.

## 🎯 What Gets Tested

### 1. Core Helius Client Methods
- ✅ `get_token_metadata()` - Token supply, decimals, and metadata
- ✅ `get_token_price_from_dex()` - Jupiter price integration
- ✅ `get_token_holders()` - Token holder analysis with rate limiting
- ✅ `parse_transactions()` - Transaction parsing via enhanced API
- ✅ `get_token_transactions()` - Token transaction history
- ✅ `get_comprehensive_transaction_history()` - Extended transaction data
- ✅ `get_historical_holder_changes()` - Paperhand/diamond hand analysis

### 2. Direct API Endpoints

#### Helius Enhanced APIs
- ✅ `POST /transactions` - Enhanced transaction parsing
- ✅ `GET /addresses/{token}/transactions` - Token-specific transactions
- ✅ `POST /rpc` - Enhanced RPC calls for token accounts

#### Solana RPC Endpoints (via Helius)
- ✅ `getTokenSupply` - Token supply information
- ✅ `getTokenLargestAccounts` - Top token holders
- ✅ `getAccountInfo` - Account details and data
- ✅ `getSignaturesForAddress` - Transaction signatures
- ✅ `getTransaction` - Detailed transaction data
- ✅ `getTokenAccounts` - Token account enumeration

#### External APIs
- ✅ `Jupiter Price API v2` - Real-time token pricing

### 3. Real Token Testing
Uses actual Solana tokens:
- `USDC` - EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
- `USDT` - Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB
- `RAY` - 4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R
- `BONK` - DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263

## 🚀 How to Run

### Setup
1. Create `.env` file with `HELIUS_API_KEY`
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `./run_helius_tests.sh` or `python test_helius_comprehensive.py`

## 📊 Test Categories
- Token Metadata (6 tests)
- Token Prices (6 tests) 
- Token Holders (5 tests)
- Transaction Parsing (3 tests)
- RPC Endpoints (4 tests)
- Error Handling (2 tests)
- Edge Cases (3 tests)
- Network Scenarios (3 tests)

## 📊 Test Output

The test suite provides detailed output including:

- ✅ **Pass/Fail Status** for each endpoint
- ⏱️ **Execution Times** for performance monitoring
- 📈 **Success Rates** by category
- 🔍 **Detailed Error Messages** for failures
- 📋 **Summary Statistics** by API category

### Sample Output
```
🚀 Starting comprehensive Helius API tests...
📊 Testing with 6 different tokens
================================================================================

📋 Testing Token Metadata API...
  ✅ Valid metadata: supply=1234567890.0, decimals=6

💰 Testing Token Price API (Jupiter)...
  ✅ Price found: $0.999842 USDC

👥 Testing Token Holders API...
  ✅ Found 10 holders in 2.34s, top holder: 98765432.12 tokens

🔍 Testing Transaction Parsing API...
  ✅ Parsed 2 transactions

📊 Testing Token Transactions API...
  ✅ Found 50 transactions in 1.87s

📈 Testing Comprehensive Transaction History API...
  ✅ Found 150 transactions in 4.23s

🔄 Testing Historical Holder Changes API...
  ✅ Analyzed 45 holders in 3.45s (📄12.3% 💎67.8%)

⏱️ Testing Rate Limiting Behavior...
  ✅ Rate limiting working: 3/5 requests limited in 15.67s

🚨 Testing Error Handling...
  ✅ Correctly raised TokenNotFoundError

🎯 Testing Edge Cases...
  ✅ Small limit handled: 1 holders

🌐 Testing Direct RPC Endpoints...
  ✅ getTokenSupply: amount=1234567890000000, decimals=6

🪐 Testing Jupiter Price API (Direct)...
  ✅ Jupiter API: EPjFWdd5... = $0.999842

⚙️ Testing Internal Helper Methods...
  ✅ Market cap calculation: $1,000,000.00

🌐 Testing Network Scenarios...
  ✅ Correctly handled malformed request

================================================================================
📊 COMPREHENSIVE TEST RESULTS SUMMARY
================================================================================
⏱️  Total execution time: 89.45 seconds
🧪 Total tests run: 48
✅ Tests passed: 46
❌ Tests failed: 2
📈 Success rate: 95.8%
```

## 🔧 Troubleshooting

### Common Issues

1. **Rate Limiting Errors**
   - These are expected and tested for popular tokens
   - The test suite handles rate limits gracefully

2. **API Key Issues**
   - Ensure your Helius API key is valid and has sufficient credits
   - Check the `.env` file format

3. **Network Timeouts**
   - Some tests may timeout on slower connections
   - This is normal behavior and tests the timeout handling

4. **Missing Dependencies**
   - Run `pip install -r requirements.txt` to install all dependencies
   - Ensure you're in the correct directory

### Expected Behaviors

- **Rate Limiting**: Popular tokens (USDC, BONK) may hit rate limits - this is tested
- **Empty Results**: Some historical queries may return empty results - this is normal
- **Timeouts**: Large holder queries may timeout - the client handles this gracefully

## 📋 Test Categories

| Category | Tests | Description |
|----------|-------|-------------|
| Token Metadata | 6 | Core token information (supply, decimals) |
| Token Prices | 6 | Jupiter API integration testing |
| Token Holders | 5 | Holder analysis with rate limit testing |
| Transaction Parsing | 3 | Enhanced API transaction parsing |
| Token Transactions | 3 | Token-specific transaction history |
| Comprehensive History | 3 | Extended transaction data collection |
| Holder Changes | 3 | Paperhand/diamond hand analysis |
| Rate Limiting | 1 | Rate limit behavior verification |
| Error Handling | 2 | Error condition testing |
| Edge Cases | 3 | Boundary condition testing |
| RPC Endpoints | 4 | Direct Solana RPC testing |
| Jupiter API | 2 | Direct Jupiter API testing |
| Internal Methods | 4 | Helper function testing |
| Network Scenarios | 3 | Network error simulation |

## 🎯 Use Cases

This test suite is perfect for:

- **Development**: Validate API integrations during development
- **Deployment**: Ensure all endpoints work in production environment
- **Monitoring**: Regular health checks of external API dependencies
- **Debugging**: Isolate issues with specific API endpoints
- **Performance**: Monitor API response times and rate limiting

## 📝 Adding New Tests

To add tests for new endpoints:

1. Add the test method to the `HeliusAPITester` class
2. Call it from `run_all_tests()`
3. Use the `record_test_pass()` and `record_test_fail()` methods
4. Follow the existing pattern for error handling and validation

## 🚨 Important Notes

- Tests use **real API calls** with actual data
- Some tests may consume Helius API credits
- Rate limiting is expected and tested behavior
- Tests validate both success and failure scenarios
- All major Helius and Jupiter endpoints are covered 