## Project Architecture Map: Pace Academy Educational Digest Pipeline

**Objective:**
Deploy a functional, zero-cost, localized AI pipeline within 48 hours to serve as a proof-of-concept for the Director of AI Integration role. The system will automate the translation of educational research into immediately applicable classroom strategies, reducing faculty prep time.

**Core User Story:**
"There is a massive flood of research that is too big and too general, so teachers find it hard to keep up with the literature. This tool cuts through all the noise and delivers a tailored, verifiable digest each month to a teacher based on their classroom and their current issues, while aligning with the Pace Academy mission. It takes the research and creates a direct application for the teacher in every subject and on every grade level to help them make changes in their practice tomorrow."

---

### 1. Infrastructure & Network Topology

* **Frontend Edge:** React Single Page Application deployed via Vercel.
* **Identity & Security:** Cloudflare Zero Trust Access. Authentication is restricted to `@paceacademy.org` via email verification.
* **Secure Routing:** Cloudflare Tunnel (`cloudflared`) mapping the public Vercel requests to the local network without inbound port configuration.
* **On-Premises Hardware:** M4 Mac Mini (48GB Unified Memory) accessed remotely via Tailscale.
* **Backend Services:** Node.js Express API.
* **Data Persistence:** PostgreSQL.
* **AI/Inference Layer:** Python pipeline communicating with a local LLM hosted via LM Studio/MLX on the Mac Mini.

### 2. Data Schema (PostgreSQL)

Authentication bypasses standard credential management by extracting the `Cf-Access-Authenticated-User-Email` header provided by Cloudflare.

```sql
CREATE TABLE faculty_profiles (
    email VARCHAR(255) PRIMARY KEY,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    discipline VARCHAR(100) NOT NULL,
    years_experience INT NOT NULL,
    tailoring_query TEXT,
    current_module TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

```

### 3. Pipeline Logic & Prompt Engineering

The core value relies on the LLM's system prompt dynamically adjusting based on database parameters to act as a "Translation Engine."

* **Ingestion:** Python scripts (`newspaper3k` / `BeautifulSoup`) scrape RSS feeds and open-access portals (e.g., Cult of Pedagogy, Edutopia). Boilerplate is stripped to extract core text.
* **Dynamic Prompt Injection:**
* *Discipline & Module:* Focuses the application of the text on the specific subject matter currently being taught.
* *Experience Level:* Novice (0-3 years) triggers prompts focused on mechanics and classroom management. Veteran (10+ years) triggers prompts focused on advanced differentiation and avoiding curriculum fatigue.
* *Institutional Alignment:* Hardcoded directive to connect the pedagogical strategy directly to the Pace Academy mission statement.


* **Output Formatting constraints:**
1. Title and verifiable hyperlink to the original source.
2. Two-sentence summary of the core concept.
3. Three actionable steps to implement in the classroom "tomorrow."
4. One concluding sentence regarding institutional mission alignment.



### 4. 48-Hour Execution Plan

**Phase 1: Local Architecture (MacBook Pro)**

* Clone existing "Speed Read" medical pipeline.
* Strip XML parsing and replace with HTML text extraction heuristics.
* Initialize SQLite for local testing to mirror the target PostgreSQL schema.
* Build lightweight React frontend (Profile setup + Dashboard).

**Phase 2: Network & Access Configuration**

* Deploy React frontend to Vercel.
* Establish Cloudflare Zero Trust policy for the `@paceacademy.org` domain.
* Initialize Cloudflare Tunnel locally to route Vercel API calls to the MacBook Pro backend.
* Implement Express middleware to parse the `Cf-Access-Authenticated-User-Email` header.

**Phase 3: Prompt Tuning & Persona Testing**

* Run local inferences using LM Studio on the MacBook Pro.
* Process a single unstructured educational article against three distinct mock personas (e.g., 1st-year middle school math vs. 15-year AP History) to verify the prompt's translation capabilities.

**Phase 4: Remote Deployment & Handoff**

* Connect to M4 Mac Mini via Tailscale SSH.
* Migrate SQLite schema to PostgreSQL instance on the Mac Mini.
* Transfer repository, configure local `.env` variables, and spin up LM Studio.
* Initialize the persistent Cloudflare Tunnel on the Mac Mini.
* Configure launch script (`start.sh`) for presentation reliability.