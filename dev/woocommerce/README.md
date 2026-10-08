# Local Reproducible WooCommerce Development Environment

This directory provides an isolated Docker Compose environment running **WordPress + MySQL** on port `8085` to develop, test, and evaluate the WooCommerce Agent Connector.

---

## Key Features & Safety Boundaries

- **Dedicated Namespace**: Runs under Docker Compose project `woo-agent-dev`.
- **Non-Default Port**: Maps to host port `8085` (leaving default port `80` and `8080` untouched).
- **Isolated Storage & Network**: Uses dedicated volumes (`woo_agent_dev_wp_data`, `woo_agent_dev_db_data`) and network (`woo_agent_dev_net`).
- **Zero Impact on Existing Environments**: Starting or tearing down this environment will not affect any existing containers (e.g., `woocommerce-test`).

---

## 1. Quickstart

### Step 1: Start the Docker Environment

```bash
docker compose -p woo-agent-dev -f dev/woocommerce/docker-compose.yml up -d
```

Verify containers are running:

```bash
docker compose -p woo-agent-dev -f dev/woocommerce/docker-compose.yml ps
```

---

### Step 2: Complete Initial WordPress Setup

1. Open your browser and navigate to:
   ```text
   http://localhost:8085
   ```
2. Select **English (United States)** and click **Continue**.
3. Fill in the site details:
   - **Site Title**: `WooCommerce Dev Store`
   - **Username**: `admin`
   - **Password**: *(choose a secure local password)*
   - **Your Email**: `admin@example.com`
4. Click **Install WordPress**, then log in to the admin dashboard.

---

### Step 3: Install & Activate WooCommerce

1. In the WordPress admin menu, navigate to **Plugins > Add New Plugin**.
2. Search for **WooCommerce**.
3. Click **Install Now**, then click **Activate**.
4. When prompted with the WooCommerce setup wizard, you can click **Skip guided setup** at the bottom.

---

### Step 4: Configure Permalinks (Mandatory for REST API)

WooCommerce REST API endpoints (`/wp-json/wc/v3/`) require non-plain URL permalinks.

1. Navigate to **Settings > Permalinks**.
2. Under **Permalink structure**, select **Post name** (`/%postname%/`).
3. Click **Save Changes**.

---

### Step 5: Generate WooCommerce REST API Keys

The connector uses separate keys for administrative seeding (read/write) and runtime agent interactions (read-only):

1. Navigate to **WooCommerce > Settings > Advanced > REST API**.
2. Click **Add key** (or **Create an API key**).

#### Key A: Seeding Key (Read/Write)
- **Description**: `Agent Seeder`
- **User**: `admin`
- **Permissions**: `Read/Write`
- Click **Generate API key**.
- Note the generated `Consumer key` (starts with `ck_`) and `Consumer secret` (starts with `cs_`).

#### Key B: Connector & Demo Key (Read-Only)
- Click **Add key**.
- **Description**: `Agent Studio Connector`
- **User**: `admin`
- **Permissions**: `Read`
- Click **Generate API key**.
- Note the generated `Consumer key` and `Consumer secret`.

---

### Step 6: Configure Project Environment (`.env`)

In the root of the repository, configure your `.env` file with your generated credentials:

```bash
# WooCommerce Store URL (Local Docker environment on port 8085)
WOO_BASE_URL="http://localhost:8085"

# Runtime Read-Only Credentials (for MCP server & agent demo)
WOO_CONSUMER_KEY="ck_your_read_only_key_here"
WOO_CONSUMER_SECRET="cs_your_read_only_secret_here"

# Administrative Read/Write Credentials (for deterministic seeding)
WOO_SEED_CONSUMER_KEY="ck_your_read_write_key_here"
WOO_SEED_CONSUMER_SECRET="cs_your_read_write_secret_here"
SEED_WOOCOMMERCE="1"

# Local Development HTTP Notice
# Allows plain HTTP for local container development.
# WARNING: Strict HTTPS is enforced in production environments.
WOO_ALLOW_INSECURE_HTTP="true"

# Groq LLM API Key (required for agent demo and evaluation runner)
GROQ_API_KEY="gsk_your_groq_api_key_here"
```

> **Security Note**: Never commit real API keys to version control. Keep credentials in `.env` (which is git-ignored).

---

### Step 7: Seed the Deterministic Dataset

Run the automated seeder to populate the store with the benchmark catalog (5 products) and order dataset (12 orders):

```bash
python -m woo_connector.seed
```

#### Idempotency Verification
Run the command a second time to verify idempotency:

```bash
python -m woo_connector.seed
```

*Expected output on second run: Reports all 5 products and 12 orders already exist with 0 newly created records.*

---

### Step 8: Verify Connector & Run Demo

Run the test suite to verify live integration:

```bash
# Run unit and integration tests
pytest -q

# Run live agent demo
python -m agent_demo
```

---

## 2. Environment Teardown & Management

To stop and remove **ONLY** this `woo-agent-dev` environment without affecting any other containers:

```bash
# Stop containers (preserves database and uploads in volumes)
docker compose -p woo-agent-dev -f dev/woocommerce/docker-compose.yml down

# Stop containers AND delete development volumes (resets store completely)
docker compose -p woo-agent-dev -f dev/woocommerce/docker-compose.yml down -v
```
