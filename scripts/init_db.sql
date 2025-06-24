-- Database initialization script for Trojan Trading Analytics
-- This creates all necessary tables if they don't exist

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create tokens table
CREATE TABLE IF NOT EXISTS tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    address VARCHAR(44) NOT NULL UNIQUE,
    name VARCHAR(100),
    symbol VARCHAR(20),
    decimals INTEGER NOT NULL DEFAULT 9,
    total_supply NUMERIC(20,9),
    creator VARCHAR(44),
    currency VARCHAR(10),
    description TEXT,
    image_url VARCHAR(500),
    external_url VARCHAR(500),
    collection_address VARCHAR(44),
    token_standard VARCHAR(50),
    is_mutable BOOLEAN,
    is_burnt BOOLEAN,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on tokens table
CREATE INDEX IF NOT EXISTS idx_tokens_address ON tokens(address);
CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON tokens(symbol);
CREATE INDEX IF NOT EXISTS idx_tokens_active ON tokens(is_active);
CREATE INDEX IF NOT EXISTS idx_tokens_created_at ON tokens(created_at);
CREATE INDEX IF NOT EXISTS idx_tokens_collection_address ON tokens(collection_address) WHERE collection_address IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tokens_token_standard ON tokens(token_standard) WHERE token_standard IS NOT NULL;

-- Add comments for enhanced metadata fields
COMMENT ON COLUMN tokens.currency IS 'Currency for token price (e.g., USDC, SOL)';
COMMENT ON COLUMN tokens.description IS 'Token description from metadata';
COMMENT ON COLUMN tokens.image_url IS 'Token image URL from metadata';
COMMENT ON COLUMN tokens.external_url IS 'External project website URL';
COMMENT ON COLUMN tokens.collection_address IS 'Collection address for NFTs';
COMMENT ON COLUMN tokens.token_standard IS 'Token standard (e.g., ProgrammableNonFungible)';
COMMENT ON COLUMN tokens.is_mutable IS 'Whether token metadata is mutable';
COMMENT ON COLUMN tokens.is_burnt IS 'Whether token is burnt/destroyed';

-- Create token transactions table
CREATE TABLE IF NOT EXISTS token_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token_id UUID NOT NULL REFERENCES tokens(id),
    signature VARCHAR(88) NOT NULL UNIQUE,
    from_address VARCHAR(44),
    to_address VARCHAR(44),
    amount NUMERIC(20,9) NOT NULL,
    transaction_type VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    fee NUMERIC(15,0),
    block_height INTEGER,
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on token transactions
CREATE INDEX IF NOT EXISTS idx_tx_token_timestamp ON token_transactions(token_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_signature ON token_transactions(signature);
CREATE INDEX IF NOT EXISTS idx_tx_type_timestamp ON token_transactions(transaction_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_from_to ON token_transactions(from_address, to_address);

-- Create token holders table
CREATE TABLE IF NOT EXISTS token_holders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token_id UUID NOT NULL REFERENCES tokens(id),
    wallet_address VARCHAR(44) NOT NULL,
    balance NUMERIC(20,9) NOT NULL,
    percentage_of_supply FLOAT,
    rank INTEGER,
    first_acquired TIMESTAMP WITH TIME ZONE,
    last_transaction TIMESTAMP WITH TIME ZONE,
    transaction_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on token holders
CREATE INDEX IF NOT EXISTS idx_holders_token_balance ON token_holders(token_id, balance);
CREATE INDEX IF NOT EXISTS idx_holders_token_rank ON token_holders(token_id, rank);
CREATE INDEX IF NOT EXISTS idx_holders_wallet ON token_holders(wallet_address);

-- Create token metrics table
CREATE TABLE IF NOT EXISTS token_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token_id UUID NOT NULL REFERENCES tokens(id),
    price_usd FLOAT,
    market_cap FLOAT,
    volume_24h FLOAT,
    price_change_24h FLOAT,
    token_velocity FLOAT,
    turnover_rate FLOAT,
    concentration_top_1 FLOAT,
    concentration_top_5 FLOAT,
    concentration_top_15 FLOAT,
    holder_count INTEGER,
    paperhand_ratio FLOAT,
    diamond_hand_ratio FLOAT,
    avg_holding_time FLOAT,
    transaction_count_24h INTEGER,
    unique_traders_24h INTEGER,
    avg_transaction_size FLOAT,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on token metrics
CREATE INDEX IF NOT EXISTS idx_metrics_token_timestamp ON token_metrics(token_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON token_metrics(timestamp);

-- Create tracking jobs table
CREATE TABLE IF NOT EXISTS tracking_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id VARCHAR(100) NOT NULL UNIQUE,
    token_addresses JSONB NOT NULL,
    interval_seconds INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    last_run_at TIMESTAMP WITH TIME ZONE,
    next_run_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    run_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100)
);

-- Create indexes on tracking jobs
CREATE INDEX IF NOT EXISTS idx_tracking_job_status ON tracking_jobs(status);
CREATE INDEX IF NOT EXISTS idx_tracking_job_next_run ON tracking_jobs(next_run_at);

-- Create token metrics cache table
CREATE TABLE IF NOT EXISTS token_metrics_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cache_key VARCHAR(200) NOT NULL UNIQUE,
    token_address VARCHAR(44) NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    data JSONB NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    accessed_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on cache table
CREATE INDEX IF NOT EXISTS idx_cache_key ON token_metrics_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON token_metrics_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_cache_token_type ON token_metrics_cache(token_address, metric_type);

-- Create analytics events table
CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    token_address VARCHAR(44) NOT NULL,
    event_data JSONB NOT NULL,
    source VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on analytics events
CREATE INDEX IF NOT EXISTS idx_events_type_timestamp ON analytics_events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_token_timestamp ON analytics_events(token_address, timestamp);

-- Create function to update updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
DROP TRIGGER IF EXISTS update_tokens_updated_at ON tokens;
CREATE TRIGGER update_tokens_updated_at
    BEFORE UPDATE ON tokens
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_token_holders_updated_at ON token_holders;
CREATE TRIGGER update_token_holders_updated_at
    BEFORE UPDATE ON token_holders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tracking_jobs_updated_at ON tracking_jobs;
CREATE TRIGGER update_tracking_jobs_updated_at
    BEFORE UPDATE ON tracking_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert some sample tokens for testing
INSERT INTO tokens (address, name, symbol, decimals) VALUES
('So11111111111111111111111111111111111111112', 'Solana', 'SOL', 9),
('DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263', 'Bonk', 'BONK', 5),
('EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm', 'dogwifhat', 'WIF', 6),
('4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R', 'Raydium', 'RAY', 6)
ON CONFLICT (address) DO NOTHING;

-- Success message
SELECT 'Database initialization completed successfully!' as message; 