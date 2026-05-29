require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 10,
  statement_timeout: 10000,   // kill any query that hangs > 10s
  idle_in_transaction_session_timeout: 15000,
});

module.exports = pool;
